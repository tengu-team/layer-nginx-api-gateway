import os
from subprocess import run, CalledProcessError
from charms.reactive import set_flag, clear_flag, when_not, when, when_any
from charms.reactive.relations import endpoint_from_flag
from charms.reactive.helpers import data_changed
from charmhelpers.core import templating
from charmhelpers.core.hookenv import status_set, log, config
from charms.reactive.flags import get_flags

########################################################################
# Installation
########################################################################


@when('nginx.available')
@when_not('gateway.setup')
def init_gateway():
    if os.path.exists('/etc/nginx/sites-enabled/default'):
        os.remove('/etc/nginx/sites-enabled/default')
    if not os.path.exists('/etc/nginx/sites-available/juju'):
        os.mkdir('/etc/nginx/sites-available/juju')
    if not os.path.exists('/etc/nginx/streams-available/juju'):
        os.makedirs('/etc/nginx/streams-available/juju')
    if not os.path.exists('/etc/nginx/streams-enabled'):
        os.makedirs('/etc/nginx/streams-enabled')
    # Append stream config block to /etc/nginx/nginx.conf
    with open("/etc/nginx/nginx.conf", "a") as f:
        f.writelines(['stream {\n',
                      '\tinclude /etc/nginx/streams-enabled/*;\n',
                      '}'])
    set_flag('gateway.setup')


########################################################################
# Upstream
########################################################################


@when('endpoint.upstream.new-upstream',
      'gateway.setup')
def upstream_changed():
    clear_flag('gateway.no-upstream')
    endpoint = endpoint_from_flag('endpoint.upstream.new-upstream')
    clear_flag('endpoint.upstream.new-upstream')
    nginx_configs = endpoint.get_nginx_configs()
    nginx_locations = endpoint.get_nginx_locations()
    nginx_streams = endpoint.get_nginx_streams()
    if (not data_changed('upstreams.nginx_configs', nginx_configs)
       and not data_changed('upstreams.nginx_locations', nginx_locations)
       and not data_changed('upstreams.nginx_streams', nginx_streams)):
        return
    clean_nginx()
    # Create nginx_config files (ex. Upstream blocks)
    create_nginx_config(nginx_configs)
    # Create a default nginx server block
    # Only one location block per juju application name is currently possible
    # If multple units of the same juju app send different location blocks, 
    # only one will be configured !
    create_location_config(nginx_locations)
    # Create streams config
    create_streams_config(nginx_streams)
    # Create symb links to /sites-enabled and /streams-enabled
    for f in os.listdir('/etc/nginx/sites-available/juju'):
        os.symlink('/etc/nginx/sites-available/juju/' + f,
                   '/etc/nginx/sites-enabled/' + f)
    for f in os.listdir('/etc/nginx/streams-available/juju'):
        os.symlink('/etc/nginx/streams-available/juju/' + f, 
                   '/etc/nginx/streams-enabled/' + f)
    if not update_nginx():
        log("UPDATE NGINX FAILED")
        return
    status_set('active', 'ready')


@when('nginx.available',
      'gateway.setup')
@when_not('endpoint.upstream.available',
          'gateway.no-upstream')
def no_upstream():
    clean_nginx()
    update_nginx()
    data_changed('upstream.services', [])
    set_flag('gateway.no-upstream')


def create_nginx_config(nginx_configs):
    for config in nginx_configs:
        if not config['nginx_config']:
            continue
        unit = config['remote_unit_name'].split('/')[0]
        with open('/etc/nginx/sites-available/juju/' + unit + '-upstreams', 'w+') as f:
            f.write(config['nginx_config'])


def create_location_config(nginx_locations):
    track_units = []
    non_duplicate_locations = []
    for location in nginx_locations:
        if not location['location_config']:
            continue
        unit = location['remote_unit_name'].split('/')[0]
        if unit not in track_units:
            track_units.append(unit)
            non_duplicate_locations.append(location['location_config'])
    if non_duplicate_locations:
        templating.render(source='server.tmpl',
                        target='/etc/nginx/sites-available/juju/server',
                        context={
                            'locations': non_duplicate_locations
                        })


def create_streams_config(nginx_streams):
    for stream in nginx_streams:
        if not stream['stream_config']:
            continue
        unit = stream['remote_unit_name'].split('/')[0]
        with open('/etc/nginx/streams-available/juju/' + unit, 'w') as f:
            f.write(stream['stream_config'])


########################################################################
# HTTP
########################################################################


@when('nginx.available',
      'website.available')
def configure_gateway_http():
    website = endpoint_from_flag('website.available')
    website.configure(port=config().get('port'))


########################################################################
# Helper functions
########################################################################


def clean_nginx():
    # Remove all juju symb links / files in
    #   - /sites-enabled
    #   - /sites-available/juju
    #   - /streams-enabled
    #   - /streams-available/juju
    for f in os.listdir('/etc/nginx/sites-available/juju'):
        if os.path.exists('/etc/nginx/sites-enabled/' + f):
            os.unlink('/etc/nginx/sites-enabled/' + f)
        os.remove('/etc/nginx/sites-available/juju/' + f)
    for f in os.listdir('/etc/nginx/streams-available/juju'):
        if os.path.exists('/etc/nginx/streams-enabled' + f):
            os.unlink('/etc/nginx/streams-enabled' + f)
        os.remove('/etc/nginx/streams-available/juju/' + f)


def update_nginx():
    # Check if nginx config is valid
    try:
        cmd = run(['nginx', '-t'])
        cmd.check_returncode()
    except CalledProcessError as e:
        log(e)
        status_set('blocked', 'Invalid NGINX configuration')
        return False
    # Reload NGINX
    try:
        cmd = run(['nginx', '-s', 'reload'])
        cmd.check_returncode()
    except CalledProcessError as e:
        log(e)
        status_set('blocked', 'Error reloading NGINX')
        return False
    return True

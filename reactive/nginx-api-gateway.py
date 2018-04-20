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
    configure_exact_server_names()
    if not os.path.exists('/etc/nginx/sites-available/juju'):
        os.mkdir('/etc/nginx/sites-available/juju')
    set_flag('gateway.setup')


@when('nginx.available',
      'website.available')
def configure_gateway():
    website = endpoint_from_flag('website.available')
    website.configure(port=config().get('port'))


@when('gateway.setup',
      'config.changed.exact-server-names')
def configure_nginx():
    configure_exact_server_names()


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
    if not data_changed('upstreams.nginx_configs', nginx_configs) \
       and not data_changed('upstreams.nginx_locations', nginx_locations):
        return
    clean_nginx()
    # Create nginx_config files ex. Upstream blocks
    for config in nginx_configs:
        if not config['nginx_config']:
            continue
        unit = config['remote_unit_name'].split('/')[0]
        with open('/etc/nginx/sites-available/juju/' + unit + '-upstreams', 'w+') as f:
            f.write(config['nginx_config'])
    # Create a nginx server block
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
    # Create symb links to /sites-enabled
    for file in os.listdir('/etc/nginx/sites-available/juju'):
        os.symlink('/etc/nginx/sites-available/juju/' + file, '/etc/nginx/sites-enabled/' + file)
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


########################################################################
# HTTP
########################################################################


@when('nginx.available',
      'endpoint.upstream.available',
      'endpoint.website.available')
def publish_website_info():
    website = endpoint_from_flag('endpoint.website.available')
    website.publish_info(80)


########################################################################
# Helper functions
########################################################################


def clean_nginx():
    # Remove all juju symb links in /sites-enabled and /sites-available/juju
    for file in os.listdir('/etc/nginx/sites-available/juju'):
        os.unlink('/etc/nginx/sites-enabled/' + file)
        os.remove('/etc/nginx/sites-available/juju/' + file)            


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


def configure_exact_server_names():
    if config().get('exact-server-names'):
        if not os.path.exists('/etc/nginx/sites-available/__exact-server-names'):
            templating.render(source="exact-server-names.tmpl",
                              target="/etc/nginx/sites-available/__exact-server-names",
                              context={})
            os.symlink('/etc/nginx/sites-available/__exact-server-names',
                       '/etc/nginx/sites-enabled/__exact-server-names')
    else:
        if os.path.exists('/etc/nginx/sites-enabled/__exact-server-names'):
            os.unlink('/etc/nginx/sites-enabled/__exact-server-names')
        if os.path.exists('/etc/nginx/sites-available/__exact-server-names'):
            os.remove('/etc/nginx/sites-available/__exact-server-names')
    update_nginx()

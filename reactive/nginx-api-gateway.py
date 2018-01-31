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


@when_any('endpoint.upstream.new-upstream')
def upstream_changed():
    clear_flag('gateway.no-upstream')
    endpoint = endpoint_from_flag('endpoint.upstream.new-upstream')
    clear_flag('endpoint.upstream.new-upstream')
    upstreams = endpoint.get_upstreams()
    if not data_changed('upstreams.services', upstreams):
        return
    clean_nginx()
    for upstream in upstreams:
        if not upstream['nginx_config']:
            continue
        unit = upstream['remote_unit_name'].split('/')[0]
        with open('/etc/nginx/sites-available/' + unit, 'w+') as f:
            f.write(upstream['nginx_config'])
    # Create symb links to /sites-enabled
    for file in os.listdir('/etc/nginx/sites-available'):
        os.symlink('/etc/nginx/sites-available/' + file, '/etc/nginx/sites-enabled/' + file)
    if not update_nginx():
        log("UPDATE NGINX FAILED")
        return
    status_set('active', 'ready')


@when('nginx.available')
@when_not('endpoint.upstream.available',
          'gateway.no-upstream')
def no_upstream():
    clean_nginx()
    update_nginx()
    data_changed('upstream.services', [])
    set_flag('gateway.no-upstream')


########################################################################
# Upstream
########################################################################


@when('endpoint.upstream.available',
      'endpoint.website.available')
def publish_website_info():
    website = endpoint_from_flag('endpoint.website.available')
    website.publish_info(80)


########################################################################
# Helper functions
########################################################################


def clean_nginx():
    # Remove all symb links in /sites-enabled
    for file in os.listdir('/etc/nginx/sites-enabled'):
        os.unlink('/etc/nginx/sites-enabled/' + file)
    # Remove all config files from /sites-available
    for file in os.listdir('/etc/nginx/sites-available'):
        os.remove('/etc/nginx/sites-available/' + file)
    configure_exact_server_names()  # Restore defautl config


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
        if not os.path.exists('/etc/nginx/sites-available/exact-server-names'):
            templating.render(source="exact-server-names.tmpl",
                              target="/etc/nginx/sites-available/exact-server-names",
                              context={})
            os.symlink('/etc/nginx/sites-available/exact-server-names',
                       '/etc/nginx/sites-enabled/exact-server-names')
    else:
        if os.path.exists('/etc/nginx/sites-enabled/exact-server-names'):
            os.unlink('/etc/nginx/sites-enabled/exact-server-names')
        if os.path.exists('/etc/nginx/sites-available/exact-server-names'):
            os.remove('/etc/nginx/sites-available/exact-server-names')
    update_nginx()

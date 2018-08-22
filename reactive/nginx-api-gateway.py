import os
from subprocess import run, CalledProcessError
from charms.reactive import set_flag, clear_flag, when_not, when, when_any
from charms.reactive.relations import endpoint_from_flag
from charms.reactive.helpers import data_changed
from charmhelpers.core.templating import render
from charmhelpers.core.hookenv import status_set, log, config
from charms.layer.nginx_config_helper import (
    NginxConfig, 
    NginxConfigError, 
    NginxModule,
)


########################################################################
# Installation
########################################################################


@when('nginx.available')
@when_not('gateway.setup')
def init_gateway():
    nginxcfg = NginxConfig()
    if os.path.exists(os.path.join(nginxcfg.http_enabled_path, 'default')):
        os.remove(os.path.join(nginxcfg.http_enabled_path, 'default'))    
    upstream_path = os.path.join(nginxcfg.http_available_path, 'upstream')
    os.makedirs(upstream_path, exist_ok=True)
    set_flag('gateway.setup')


########################################################################
# Upstream
########################################################################


@when('endpoint.upstream.new-upstream',
      'gateway.setup')
def upstream_changed():
    clear_flag('gateway.no-upstream')
    endpoint = endpoint_from_flag('endpoint.upstream.new-upstream')
    
    nginx_configs = endpoint.get_nginx_configs()
    nginx_locations = endpoint.get_nginx_locations()
    
    if (not data_changed('upstreams.nginx_configs', nginx_configs)
       and not data_changed('upstreams.nginx_locations', nginx_locations)):
        return
    try:
        nginxcfg = NginxConfig()
        nginxcfg.delete_all_config(NginxModule.HTTP, subdir='upstream')
        # Create nginx_config files (ex. Upstream blocks)
        create_nginx_config(nginxcfg, nginx_configs)
        # Create a default nginx server block
        # Only one location block per juju application name is currently possible
        # If multple units of the same juju app send different location blocks, 
        # only one will be configured !
        create_location_config(nginxcfg, nginx_locations)
        # Create symb links to /sites-enabled
        nginxcfg.enable_all_config(NginxModule.HTTP, subdir='upstream') \
                .validate_nginx() \
                .reload_nginx()
    except NginxConfigError as e:
        log(e)
        status_set('blocked', '{}'.format(e))
        return
    clear_flag('endpoint.upstream.new-upstream')
    status_set('active', 'ready')


@when('nginx.available',
      'gateway.setup')
@when_not('endpoint.upstream.available',
          'gateway.no-upstream')
def no_upstream():
    nginxcfg = NginxConfig()
    nginxcfg.delete_all_config(NginxModule.HTTP, subdir='upstream') \
            .validate_nginx() \
            .reload_nginx()
    #data_changed('upstream.services', [])
    set_flag('gateway.no-upstream')


def create_nginx_config(nginxcfg, nginx_configs):
    for config in nginx_configs:
        if not config['nginx_config']:
            continue
        unit = config['remote_unit_name'].split('/')[0]
        nginxcfg.write_config(NginxModule.HTTP,
                              config['nginx_config'], 
                              unit + '-upstream', 
                              subdir='upstream')


def create_location_config(nginxcfg, nginx_locations):
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
        cfg = render(source='server.tmpl',
                     target=None,
                     context={
                          'locations': non_duplicate_locations
                    })
        nginxcfg.write_config(NginxModule.HTTP,
                              cfg,
                              'server-upstream',
                              subdir='upstream')


########################################################################
# HTTP
########################################################################


@when('nginx.available',
      'website.available')
def configure_gateway_http():
    website = endpoint_from_flag('website.available')
    website.configure(port=config().get('port'))

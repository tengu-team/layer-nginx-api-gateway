# Overview
This charm installs and configures [NGINX](https://nginx.org/en/). You can send (NGINX) config files to this charm and NGINX will be updated to add / remove these configurations. You can use this to expose microservices using an API gateway via Juju charms.

# Usage
Deploy the gateway with the following:

`juju deploy ./nginx-api-gateway`

Add a relation with a charm that provides an [upstream](https://github.com/tengu-team/interface-upstream) interface.

`juju add-relation nginx-api-gateway service`

# Default behaviour
- All nginx [location](http://nginx.org/en/docs/http/ngx_http_core_module.html#location) blocks will be merged into a single server block in `/etc/nginx/juju/{juju-application-name-unitnr}/nginx-api-gateway/sites-available/upstream/server-upstream`.
- Do not store manual configurations in `/etc/nginx/juju`. Configs can be removed when an upstream relation is changed.

## Authors

This software was created in the [IDLab research group](https://www.ugent.be/ea/idlab) of [Ghent University](https://www.ugent.be) in Belgium. This software is used in [Tengu](https://tengu.io), a project that aims to make experimenting with data frameworks and tools as easy as possible.

 - Sander Borny <sander.borny@ugent.be>

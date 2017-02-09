import sys
import os
from distutils.core import setup, Extension

packages = ['cancat']
mods = []
pkgdata = {}
scripts = ['CanCat.py']

setup  (name        = 'cancat',
        version     = '1.0',
        description = "Swiss army knife of Controller Area Networks (CAN) often used in cars and building automation, etc...",
        author = 'atlas of d00m',
        author_email = 'atlas@r4780y.com',
        #include_dirs = [],
        packages  = packages,
        package_data = pkgdata,
        ext_modules = mods,
        scripts = scripts
       )



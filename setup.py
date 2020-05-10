import sys
import os
from distutils.core import setup, Extension

packages = ['cancat','cancat/vstruct']
mods = []
pkgdata = {}
scripts = ['CanCat.py']

setup  (name        = 'cancat',
        version     = '1.0',
        description = "Multi-purpose tool for interacting with Controller Area Networks (CAN)",
        author = 'atlas of d00m',
        author_email = 'atlas@r4780y.com',
        #include_dirs = [],
        packages  = packages,
        package_data = pkgdata,
        ext_modules = mods,
        scripts = scripts
       )



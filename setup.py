import sys
import os
import codecs
import setuptools

version = '1.0.1'
packages = ['cancat','cancat/vstruct']
mods = []
pkgdata = {}
scripts = ['CanCat.py']

requirements = open('requirements.txt').read().split('\n')

# Readme function to show readme as a description in pypi
def readme():
    with codecs.open('README.md', encoding='utf-8') as f:
        return f.read()

setuptools.setup  (name  = 'cancat',
        version          = version,
        description      = "Multi-purpose tool for interacting with Controller Area Networks (CAN) and SAE J1939",
        long_description = readme(),
        author           = 'atlas of d00m',
        author_email     = 'atlas@r4780y.com',
        url              = 'https://github.com/atlas0fd00m/CanCat',
        download_url     = 'https://github.com/atlas0fd00m/rfcat/archive/v%s.tar.gz' % version,
        keywords         = ['can', 'controller area network', 'automotive', 'j1939', 'hacking', 'reverse engineering'],
        packages         = setuptools.find_packages(),
        package_data     = pkgdata,
        ext_modules      = mods,
        scripts          = scripts,
        install_requires = requirements,
        classifiers      = [
                            # How mature is this project? Common values are
                            #   3 - Alpha
                            #   4 - Beta
                            #   5 - Production/Stable
                            'Development Status :: 5 - Production/Stable',

                            # Indicate who your project is intended for: See info here: https://pypi.org/classifiers
                            'Intended Audience :: Telecommunications Industry',
                            'Topic :: Communications',

                            # Pick your license as you wish (should match "license" above)
                            'License :: OSI Approved :: BSD License',

                            # Specify the Python versions you support here. In particular, ensure
                            # that you indicate whether you support Python 2, Python 3 or both.
                            'Programming Language :: Python :: 2',
                            'Programming Language :: Python :: 2.7',
                            #'Programming Language :: Python :: 3',
                            #'Programming Language :: Python :: 3.8',
                            #'Operating System :: OS Indepentent',
                           ],
        python_requires  = '>=2.7'
        )

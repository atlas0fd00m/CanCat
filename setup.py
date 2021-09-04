import sys
import os
import codecs
import setuptools

version = '1.9.1'
packages = ['cancat','cancat/vstruct']
mods = []
pkgdata = {}
scripts = ['CanCat.py', 'J1939Cat']

requirements = open('requirements.txt').read().split('\n')

# Readme function to show readme as a description in pypi
def readme():
    with codecs.open('README.md', encoding='utf-8') as f:
        return f.read()

setuptools.setup  (name  = 'cancat',
        version          = version,
        description      = "Multi-purpose tool for interacting with Controller Area Networks (CAN) and SAE J1939",
        long_description = readme(),
        long_description_content_type='text/markdown',
        author           = 'atlas of d00m and the GRIMM CyPhy team',
        author_email     = 'atlas@r4780y.com',
        url              = 'https://github.com/atlas0fd00m/CanCat',
        download_url     = 'https://github.com/atlas0fd00m/CanCat/archive/v%s.tar.gz' % version,
        keywords         = ['can', 'controller area network', 'automotive', 'j1939', 'hacking', 'reverse engineering'],
        packages         = setuptools.find_packages(),
        package_data     = pkgdata,
        ext_modules      = mods,
        scripts          = scripts,
        install_requires = requirements,
        classifiers      = [
                            'Development Status :: 5 - Production/Stable',
                            'Intended Audience :: Telecommunications Industry',
                            'Topic :: Communications',
                            'License :: OSI Approved :: BSD License',
                            'Programming Language :: Python :: 3',
                            'Programming Language :: Python :: 3.6',
                            'Programming Language :: Python :: 3.7',
                            'Programming Language :: Python :: 3.8',
                            'Programming Language :: Python :: 3.9',
                           ],
        python_requires  = '>=3.6'
        )

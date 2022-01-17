import os
import sys
import codecs
import setuptools

VERSION = open('VERSION').read().strip()
packages = ['cancat','cancat/vstruct']
mods = []
pkgdata = {}
scripts = ['CanCat', 'J1939Cat', 'canmap', 'cancat2candump', 'cancat2pcap', 'candump2cancat']

dirn = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(dirn, 'README.md'), 'r') as fd:
    desc = fd.read()

setuptools.setup  (name  = 'cancat',
        version          = VERSION,
        description      = "Multi-purpose tool for interacting with Controller Area Networks (CAN) and SAE J1939",
        long_description = desc,
        long_description_content_type='text/markdown',
        author           = 'atlas of d00m and the GRIMM CyPhy team',
        author_email     = 'atlas@r4780y.com',
        url              = 'https://github.com/atlas0fd00m/CanCat',
        download_url     = 'https://github.com/atlas0fd00m/CanCat/archive/v%s.tar.gz' % VERSION,
        keywords         = ['can', 'controller area network', 'automotive', 'j1939', 'hacking', 'reverse engineering'],
        packages         = setuptools.find_packages(),
        package_data     = pkgdata,
        ext_modules      = mods,
        scripts          = scripts,
        install_requires = [    
                "ipython",
                "pyserial",
                "pyusb",
                "termcolor",
                "future",
                "six",
            ],
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

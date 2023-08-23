from setuptools import setup, find_packages

with open("requirements.txt", "r") as f:
    requirements = f.read().splitlines()

setup(
    name="pymumble-typed",
    version="1.2.5",
    author='nico9889',
    author_email='contact@nico9889.me',
    description="Mumble library used for multiple uses like making mumble bot.",
    long_description="",
    long_description_content_type="text/markdown",
    url='https://github.com/Mello-Bot/pymumble-typed',
    license='GPLv3',
    packages=find_packages(),
    install_requires=requirements,
    include_package_data=True,
    classifiers=["Programming Language :: Python :: 3",
                 "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
                 "Operating System :: OS Independent",
                 ],
    python_requires='>=3.8',
    data_files=[('', ['LICENSE', 'requirements.txt'])],
)


build: ##build python patckage
	python setup.py sdist bdist_wheel

list: ##list all files from archive file of python package
	tar tzf dist/awsinsights-1.0.0.tar.gz

check: #check python package using twine tool
	twine check dist/*

publish: build list check #publish python package to PyPI using twine tool
	twine upload -r pypi dist/*

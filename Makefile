
build: clean ##build python patckage
	python setup.py sdist bdist_wheel

check: #check python package using twine tool
	twine check dist/*

publish: build check #publish python package to PyPI using twine tool
	twine upload -r pypi dist/*

clean:
	rm -rf awsinsights.egg-info build dist

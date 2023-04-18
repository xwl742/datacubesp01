Docker for running test suite
=============================

- Pushed to docker hub as `opendatacube/datacube-tests`

Example Use:

```shell
git clone https://github.com/opendatacube/datacube-core.git
cd datacube_sp-core
docker run --rm \
  -v $(pwd):/code \
  opendatacube/datacube_sp-tests:latest \
  ./check-code.sh integration_tests
```

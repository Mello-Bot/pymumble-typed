#!/bin/bash
python -m grpc_tools.protoc -I=./protobuf --python_out=./src/pymumble_typed/protobuf --pyi_out=./src/pymumble_typed/protobuf protobuf/*.proto
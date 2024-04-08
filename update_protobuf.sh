#!/bin/bash

protoc --proto_path=./protobuf --python_out=./pymumble_typed/protobuf protobuf/Mumble.proto protobuf/MumbleUDP.proto --mypy_out=./pymumble_typed/protobuf
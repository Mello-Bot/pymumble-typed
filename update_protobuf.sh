#!/bin/bash

protoc --proto_path=./protobuf --python_out=./pymumble-typed protobuf/Mumble.proto protobuf/MumbleUDP.proto --mypy_out=./pymumble-typed
# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: MumbleUDP.proto
# Protobuf Python Version: 6.30.0
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC,
    6,
    30,
    0,
    '',
    'MumbleUDP.proto'
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x0fMumbleUDP.proto\x12\tMumbleUDP\"\xc2\x01\n\x05\x41udio\x12\x10\n\x06target\x18\x01 \x01(\rH\x00\x12\x11\n\x07\x63ontext\x18\x02 \x01(\rH\x00\x12\x16\n\x0esender_session\x18\x03 \x01(\r\x12\x14\n\x0c\x66rame_number\x18\x04 \x01(\x04\x12\x11\n\topus_data\x18\x05 \x01(\x0c\x12\x17\n\x0fpositional_data\x18\x06 \x03(\x02\x12\x19\n\x11volume_adjustment\x18\x07 \x01(\x02\x12\x15\n\ris_terminator\x18\x10 \x01(\x08\x42\x08\n\x06Header\"\xa6\x01\n\x04Ping\x12\x11\n\ttimestamp\x18\x01 \x01(\x04\x12$\n\x1crequest_extended_information\x18\x02 \x01(\x08\x12\x19\n\x11server_version_v2\x18\x03 \x01(\x04\x12\x12\n\nuser_count\x18\x04 \x01(\r\x12\x16\n\x0emax_user_count\x18\x05 \x01(\r\x12\x1e\n\x16max_bandwidth_per_user\x18\x06 \x01(\rB\x02H\x01\x62\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'MumbleUDP_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  _globals['DESCRIPTOR']._loaded_options = None
  _globals['DESCRIPTOR']._serialized_options = b'H\001'
  _globals['_AUDIO']._serialized_start=31
  _globals['_AUDIO']._serialized_end=225
  _globals['_PING']._serialized_start=228
  _globals['_PING']._serialized_end=394
# @@protoc_insertion_point(module_scope)

# -*- coding: utf-8 -*-
"""导出 pb2 descriptor 摘要（旧/新比较用）"""
import json
import sys

from google.protobuf.descriptor_pb2 import FieldDescriptorProto

from shared.proto import evaluation_service_pb2 as ev
from shared.proto import report_service_pb2 as rp


def dump(mod):
    out = {'messages': {}, 'services': {}}
    for name, msg in mod.DESCRIPTOR.message_types_by_name.items():
        out['messages'][name] = [
            (f.name, f.number, f.type, f.is_repeated,
             f.message_type.full_name if f.message_type else None,
             f.enum_type.full_name if f.enum_type else None)
            for f in msg.fields]
    for name, svc in mod.DESCRIPTOR.services_by_name.items():
        out['services'][name] = [
            (m.name, m.input_type.full_name, m.output_type.full_name)
            for m in svc.methods]
    return out


payload = {'evaluation': dump(ev), 'report': dump(rp)}
sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1))

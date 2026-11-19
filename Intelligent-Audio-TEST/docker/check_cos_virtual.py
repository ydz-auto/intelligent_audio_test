import os

import boto3
from botocore.config import Config

client = boto3.client(
    's3',
    endpoint_url=os.environ['OSS_ENDPOINT'],
    aws_access_key_id=os.environ['OSS_ACCESS_KEY'],
    aws_secret_access_key=os.environ['OSS_SECRET_KEY'],
    region_name=os.environ['OSS_REGION'],
    config=Config(s3={'addressing_style': 'virtual'}),
)

bucket = os.environ['OSS_BUCKET_NAME']
key = 'test/intelligent_audio_test/temp/deploy-check.txt'
client.put_object(Bucket=bucket, Key=key, Body=b'iat-deploy-check')
print('put OK')
print('get', client.get_object(Bucket=bucket, Key=key)['Body'].read())
client.delete_object(Bucket=bucket, Key=key)
print('deleted')

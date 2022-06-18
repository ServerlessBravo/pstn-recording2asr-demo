import os
import time
import sys
import json
import logging
import base64

parent_dir = os.path.abspath(os.path.dirname(__file__))
vendor_dir = os.path.join(parent_dir, 'vendor')
sys.path.insert(1, vendor_dir)

from requests import get  # noqa: E402
from urllib.parse import urlparse  # noqa: E402
from qcloud_cos import CosS3Client  # noqa: E402
from qcloud_cos import CosConfig  # noqa: E402
from qcloud_cos import CosServiceError  # noqa: E402

from tencentcloud.common import credential  # noqa: E402
from tencentcloud.common.profile.client_profile import ClientProfile  # noqa: E402
from tencentcloud.common.profile.http_profile import HttpProfile  # noqa: E402
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException  # noqa: E402
from tencentcloud.asr.v20190614 import asr_client, models  # noqa: E402

tencent_cos_client = None
tencent_asr_client = None


def download_handler(event, context):
    # trigger from apigw
    callback_event = json.loads(event['body'])
    print("receive context:", json.dumps(context))
    print("call back event:", callback_event)
    recordUrl = callback_event.get('recordUrl')
    if(recordUrl is None):
        return("Invalid callback data, missing the field of recordUrl")

    local_file_path = __tmp_filename(recordUrl)
    __download_raw_recording(recordUrl, local_file_path)

    global tencent_cos_client
    if(tencent_cos_client is None):
        tencent_cos_client = __init_cos_client(context)
    return __upload_to_cos(context, tencent_cos_client, local_file_path)


def asr_handler(event, context):
    # trigger from cos
    print("receive context:", json.dumps(context))
    cos_event = event['Records'][0]
    print("cos event:", cos_event)

    if(cos_event is None):
        return("Invalid event data, it is not trigger from cos")

    global tencent_cos_client
    if(tencent_cos_client is None):
        tencent_cos_client = __init_cos_client(context)

    cos_bucket, cos_object = cos_event['cos']['cosBucket'], cos_event['cos']['cosObject']
    appid, bucket_name, raw_key, = cos_bucket['appid'], cos_bucket['name'], cos_object['key']

    file_key = raw_key.replace("/%s/%s" % (appid, bucket_name), '')
    local_path = __tmp_filename(file_key)
    __download_from_cos(context, tencent_cos_client, file_key, local_path)

    global tencent_asr_client
    if(tencent_asr_client is None):
        tencent_asr_client = __init_asr_client(context)

    resp = __create_asr_task(tencent_asr_client, local_path)
    task_id = resp.Data.TaskId
    result = __wait_for_asr_result(tencent_asr_client, task_id)
    converted_result = result.Data.Result
    print("---------------- converted result ---------------")
    print(converted_result)
    print("-------------------------------------------------")
    return converted_result


def __wait_for_asr_result(tenent_asr_client, task_id):
    req = models.DescribeTaskStatusRequest()
    req.from_json_string(json.dumps({"TaskId": task_id}))

    while(True):
        resp = tenent_asr_client.DescribeTaskStatus(req)
        if(resp.Data.Status == 2 or resp.Data.Status == 3):
            print('asr task %s is finished' % task_id)
            return resp
        else:
            print('waiting for asr task %s to finish...' % task_id)
            time.sleep(1)


def __os_environ(context, *keys):
    env_str = context.get('environment')
    env_hash = json.loads(env_str)
    return [env_hash.get(k) for k in keys]


def __init_cos_client(context):
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    secret_id, secret_key, token, region = __os_environ(
                                                context,
                                                'TENCENTCLOUD_SECRETID',
                                                'TENCENTCLOUD_SECRETKEY',
                                                'TENCENTCLOUD_SESSIONTOKEN',
                                                'REGION')
    print("init cos client with secret_id:%s, secret_key:%s, token:%s, region:%s" % (secret_id, secret_key, token, region))
    config = CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key, Token=token)
    return CosS3Client(config)


def __init_asr_client(context):
    secret_id, secret_key, token = __os_environ(context, 'TENCENTCLOUD_SECRETID', 'TENCENTCLOUD_SECRETKEY', 'TENCENTCLOUD_SESSIONTOKEN')
    cred = credential.Credential(secret_id, secret_key, token=token)
    httpProfile = HttpProfile()
    httpProfile.endpoint = "asr.tencentcloudapi.com"

    clientProfile = ClientProfile()
    clientProfile.httpProfile = httpProfile
    return asr_client.AsrClient(cred, "", clientProfile)


def __tmp_filename(url):
    return os.path.join('/tmp', __file_basename(urlparse(url).path))


def __file_basename(path):
    return os.path.basename(path)


def __download_raw_recording(url, path):
    print("Downloading file from %s to %s " % (url, path))
    with open(path, "wb") as file:
        response = get(url)
        file.write(response.content)


def __download_from_cos(context, cos_client, key, local_path):
    target_bucket_name = __os_environ(context, "TARGET_BUCKET_NAME")[0]
    print("downloading file from cos, bucket: %s, key: %s, local: %s" % (target_bucket_name, key, local_path))
    response = cos_client.get_object(
            Bucket=target_bucket_name,
            Key=key,
            )
    response['Body'].get_stream_to_file(local_path)


def __upload_to_cos(context, cos_client, local_path):
    target_bucket_name, target_bucket_path = __os_environ(context, "TARGET_BUCKET_NAME", "TARGET_BUCKET_PATH")
    file_key = "%s/%s" % (target_bucket_path, __file_basename(local_path))
    print("uploading file from local:%s to remote:%s of COS bucket: %s" % (local_path, file_key, target_bucket_name))
    try:
        with open(local_path, 'rb') as fp:
            response = cos_client.put_object(
                    Bucket=target_bucket_name,
                    Body=fp,
                    Key=file_key,
                    StorageClass='STANDARD',
                    EnableMD5=False
                    )
            print("cos response: %s" % response)

        url = cos_client.get_object_url(
                Bucket=target_bucket_name,
                Key=file_key
                )
        return {'url': url, 'bucket_name': target_bucket_name, 'key': file_key}
    except (CosServiceError) as e:
        print(e.get_error_msg())
        raise e


def __create_asr_task(asr_client, local_path):
    try:
        req = models.CreateRecTaskRequest()

        with open(local_path, "rb") as f:
            recording_data = base64.b64encode(f.read()).decode('ascii')
            params = {
                    "EngineModelType": "8k_zh",
                    "ChannelNum": 2,
                    "ResTextFormat": 2,
                    "SourceType": 1,
                    "Data": recording_data
                    }
        req.from_json_string(json.dumps(params))
        resp = asr_client.CreateRecTask(req)
        print(resp.to_json_string())
        return resp

    except TencentCloudSDKException as err:
        print(err)

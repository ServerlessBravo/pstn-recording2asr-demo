## PSTN Call Record to Text with ASR

`PSTN`电话挂断之后，自动触发回调函数，下载录音文件到COS，然后通过COS触发器触发 语音转换函数执行。

示例：

```text
---------------- converted result ---------------

[0:0.420,0:1.130,1]  喂。

[0:1.620,0:3.410,0]  哎，对，警方能听到吧。

[0:4.160,0:5.630,1]  哎，能听到能听到。

[0:5.680,0:7.390,0]  嗯，行行行好嗯。

[0:7.390,0:9.410,0]  嗯，没事就测一下好吧。嗯。

[0:9.620,0:11.190,1]  嗯，好的好的好的。

[0:10.960,0:12.170,0]  好好好，拜拜。

[0:11.190,0:11.770,1]  嗯。

[0:12.280,0:13.690,1]  嗯嗯，拜拜。

-------------------------------------------------
```

## 函数1: PSTN 下载回调函数

基础配置：

```

函数名称	pstn_demo_callback
地域    广州
函数类型    Event函数
运行环境	Python 3.7
描述	download PSTN recordings to COS

```

环境配置:

```
内存	512MB
初始化超时时间	65秒
执行超时时间	30秒
环境变量	
REGION=ap-guangzhou
TARGET_BUCKET_NAME=demo-test-xxxx
TARGET_BUCKET_PATH=/call_recordings
```

触发器配置:

```
启用集成响应	未启用
启用Base64编码	未启用
支持CORS	否
后端超时	30s
标签	未启用
访问路径    https://service-xxx-xxx.gz.apigw.tencentcs.com/release/pstn_demo_callback
```

## 函数2: 录音转文字函数

基础配置：

```
函数名称	pstn-recording-2-asr
地域	广州
函数类型	Event函数
运行环境	Python 3.7
```

环境配置：

```
内存	512MB
初始化超时时间	65秒
执行超时时间	60秒
环境变量	
REGION=ap-guangzhou
TARGET_BUCKET_NAME=demo-test-xxx
TARGET_BUCKET_PATH=/call_recordings
```

触发器配置：

```
存储桶	demo-test-xxx.cos.ap-guangzhou.myqcloud.com
触发事件	全部创建(cos:ObjectCreated:*)
前缀过滤	call_recordings/
后缀过滤	
```
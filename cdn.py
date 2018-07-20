#!/usr/bin/python2.7
# -*- coding:utf-8 -*-

import sys,os,gzip,json,requests,urllib
import base64,hmac,time,uuid,ConfigParser
from hashlib import sha1

download_path=os.path.join(os.path.dirname(os.path.abspath(__file__)),"download")
cdn_server_address = 'https://cdn.aliyuncs.com'

class read_config(object):
    '''
    解析配置文件
    '''
    def __init__(self):
        self._CONFIGFILE=os.path.join(os.path.dirname(os.path.abspath(__file__)), "aliyun.ini")
        self._config=ConfigParser.ConfigParser()
        self._config.read(self._CONFIGFILE)
        self._access_id = self._config.get('Credentials', 'accesskeyid')
        self._access_key = self._config.get('Credentials', 'accesskeysecret')
        self._Action = self._config.get('Must', 'Action')
        self._DomainName = self._config.get('Must', 'DomainName')
        self._Must_list=self._config.items('Select')
        self._user_param={}

    @property
    def access_key_id(self):
        return self._access_id

    @property
    def access_key_secret(self):
        return self._access_key

    @property
    def user_params(self):
        if self._Action and self._DomainName:
            self._user_param['Action'] = self._Action
            self._user_param['DomainName'] = self._DomainName
            for i in self._Must_list:
                self._user_param[i[0]] = i[1]
            return self._user_param

class read_write(object):
    '''
    保存已下载过的日志
    '''
    def __init__(self):
        self._logfilename = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".download")

    @property
    def read(self):
        try:
            with open(self._logfilename, 'rb', ) as f:
                logfile = f.read()
                logfile = json.loads(logfile)
                if len(logfile) > 20:
                    logfile.pop(0)
            return logfile
        except IOError as f:
            return []

    def write(self,logfile):
        with open(self._logfilename, "wb") as f:
            file = json.dumps(logfile)
            f.write(file)

class GZipTool(object):
    """
    压缩与解压gzip
    """

    def __init__(self, bufSize=1024 * 8):
        self.bufSize = bufSize
        self.fin = None
        self.fout = None

    def compress(self, src, dst):
        self.fin = open(src, 'rb')
        self.fout = gzip.open(dst, 'wb')
        self.__in2out()

    def decompress(self, gzFile, dst):
        self.fin = gzip.open(gzFile, 'rb')
        self.fout = open(dst, 'wb')
        self.__in2out()

    def __in2out(self, ):
        while True:
            buf = self.fin.read(self.bufSize)
            if len(buf) < 1:
                break
            self.fout.write(buf)
        self.fin.close()
        self.fout.close()

def percent_encode(str):
    res = urllib.quote(str.decode('UTF-8').encode('utf8'), '')
    res = res.replace('+', '%20')
    res = res.replace('*', '%2A')
    res = res.replace('%7E', '~')
    return res

def compute_signature(parameters, access_key_secret):
    '''
    :param parameters: 生成签名需要的数据
    :param access_key_secret: 访问阿里云需要的key
    :return: 返回签名信息
    '''
    sortedParameters = sorted(parameters.items(), key=lambda parameters: parameters[0])
    canonicalizedQueryString = ''
    for (k,v) in sortedParameters:
        canonicalizedQueryString += '&' + percent_encode(k) + '=' + percent_encode(v)
    stringToSign = 'GET&%2F&' + percent_encode(canonicalizedQueryString[1:])
    h = hmac.new(access_key_secret + "&", stringToSign, sha1)
    signature = base64.encodestring(h.digest()).strip()
    return signature

def compose_url(user_params,readconfig):
    '''
    :param user_params: 生成第一次请求URL所需要的参数
    :param readconfig: 配置文件对象
    :return: 第一次请求的URL
    '''
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    parameters = { \
            'Format'        : 'JSON', \
            'Version'       : '2014-11-11', \
            'AccessKeyId'   : readconfig.access_key_id, \
            'SignatureVersion'  : '1.0', \
            'SignatureMethod'   : 'HMAC-SHA1', \
            'SignatureNonce'    : str(uuid.uuid1()), \
            'TimeStamp'         : timestamp, \
   }
    for key in user_params.keys():
        if  user_params[key]:
            parameters[key] = user_params[key]
    signature = compute_signature(parameters, readconfig.access_key_secret)
    parameters['Signature'] = signature
    url = cdn_server_address + "/?" + urllib.urlencode(parameters)
    return url

def make_request(user_params,readconfig,readwrite):
    '''
    :param user_params: 生成第一次请求URL所需要的参数
    :param readconfig: 配置文件对象
    :param readwrite: 读取和保存已下载过的文件对象
    :return: 返回一个字典，key为日志文件名，value为日志的URL地址
    '''
    url = compose_url(user_params,readconfig)
    path_dic={}
    try:
        res=requests.get(url)
        res=res.json()
        res=res['DomainLogModel']['DomainLogDetails']['DomainLogDetail']
        logfile = readwrite.read
        for i in res:
            if i['LogName'] not in logfile:
                logfile.append(i['LogName'])
                path_dic[i['LogName']]=i['LogPath']
        readwrite.write(logfile)
        return path_dic
    except Exception:
        return False

def download(download_path,user_params,readconfig,readwrite):
    '''
    :param download_path: 日志URL
    :param user_params: 生成第一次请求URL所需要的参数
    :param readconfig: 配置文件对象
    :param readwrite: 读取和保存已下载过的文件对象
    :return:
    '''
    link_path=make_request(user_params,readconfig,readwrite)
    if link_path:
        for name,path in link_path.items():
            filename=os.path.join(download_path,name)
            logname=filename[:-3]+'.txt'
            pathurl="https://%s" %path
            r = requests.get(pathurl)
            with open(filename, 'wb') as f:
                f.write(r.content)
            GZipTool().decompress(filename, logname)
            os.remove(filename)
    os.system("find %s -type f -mtime +7 |xargs rm -rf" % download_path)

if __name__ == '__main__':
    readconfig = read_config()
    user_params = readconfig.user_params
    readwrite=read_write()
    if not readconfig.user_params:
        sys.exit(1)
    else:
        download(download_path,user_params,readconfig,readwrite)
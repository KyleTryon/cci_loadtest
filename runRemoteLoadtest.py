#!/usr/bin/env python3
"""
runs a loadtest using Neocortix loadtest service
"""
# standard library modules
import argparse
#import concurrent.futures
import csv
import datetime
import json
import logging
import os
import random
import re
import requests
import shutil
import subprocess
import sys
import time
# third-party modules
#import dateutil
#import dateutil.parser
#import pandas as pd
# neocortix modules


logger = logging.getLogger(__name__)


def ncscReqHeaders( authToken ):
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Neocortix-Cloud-API-Version": "1",
        "X-Neocortix-Cloud-API-AuthToken": authToken
    }

def startTest( testsUrl, reqParams, authToken ):
    reqDataStr = json.dumps( reqParams )
    #logger.debug( 'reqDataStr: %s', reqDataStr )
    resp = requests.post( testsUrl, data=reqDataStr, headers=ncscReqHeaders(authToken) )
    logger.info( 'POST status_code %d', resp.status_code )
    logger.info( 'POST text %s', resp.text )
    respJson = resp.json()
    #logger.info( 'POST json %s', respJson )
    testId = respJson['id']
    return testId

def downloadDataFile(url, dataDirPath):
    local_filename = dataDirPath + '/' + url.split('/')[-1]
    headers = ncscReqHeaders(args.authToken)
    headers[ 'Accept' ] = 'application/json, text/html, image/*'
    # make request with stream=True
    with requests.get(url, stream=True, headers=headers) as r:
        logger.info( 'status_code %d for url %s', r.status_code, url )
        r.raise_for_status()
        with open(local_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192): 
                if chunk: # filter out keep-alive new chunks
                    f.write(chunk)
                    # f.flush()
    return

def downloadDataFileNoExc(url, dataDirPath):
    try:
        downloadDataFile( url, dataDirPath )
    except Exception as exc:
        logger.warning( 'exception (%s) downloading; %s', type(exc), exc )

def genXml():
    '''preliminary version generates "fake" junit-style xml'''
    template = '''<?xml version="1.0" ?>
<testsuites>
    <testsuite tests="1" errors="0" failures="0" name="loadtests" >
        <testcase classname="com.neocortix.loadtest" name="loadtest" time="1.0">
            <system-out>
                I am stdout!
            </system-out>
            <system-err>
                I am stderr!
            </system-err>
        </testcase>
    </testsuite>
</testsuites>
    '''
    return template

if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s %(levelname)s %(module)s %(funcName)s %(message)s', datefmt='%Y/%m/%d %H:%M:%S')
    logger.setLevel(logging.INFO)
    logger.debug('the logger is configured')

    ap = argparse.ArgumentParser( description=__doc__, fromfile_prefix_chars='@' )
    ap.add_argument( 'victimHostUrl', help='url of the host to target as victim' )
    ap.add_argument( '--authToken', required=True, help='the NCS authorization token to use' )
    ap.add_argument( '--altTargetHostUrl', help='an alternative target host URL for comparison' )
    ap.add_argument('--jsonOut', help='file path to write detailed info in json format')
    ap.add_argument( '--masterUrl', default='https://load-test.cloud.neocortix.com/', help='url of the master' )
    ap.add_argument( '--nWorkers', type=int, default=1, help='the # of worker instances to launch (or zero for all available)' )
    ap.add_argument( '--rampUpRate', type=float, default=0, help='# of simulated users to start per second (overall)' )
    ap.add_argument( '--regions', nargs='*', help='list of geographic regions (or none for all regions)' )
    ap.add_argument( '--reqMsprMean', type=float, default=1000, help='required ms per response' )
    ap.add_argument( '--susTime', type=int, default=10, help='time to sustain the test after startup (in seconds)' )
    ap.add_argument( '--targetUris', nargs='*', help='list of URIs to target' )
    ap.add_argument( '--usersPerWorker', type=int, default=6, help='# of simulated users per worker' )
    args = ap.parse_args()

    dataDirPath = 'data'
    os.makedirs( dataDirPath, exist_ok=True )

    logger.info( 'args.altTargetHostUrl: %s', args.altTargetHostUrl )

    masterUrl = args.masterUrl
    logger.info( 'testing connectivity to masterUrl: %s', masterUrl )

    # get '/' to test connectivity
    resp = requests.get( masterUrl+'/' )
    logger.info( 'resp.status_code %d', resp.status_code )
    # dont' print the text; that would be the web page source
    #logger.info( 'resp.text %s', resp.text )

    newApi = True
    if newApi:
        testsUrl = 'https://cloud.neocortix.com/cloud-api/load-test/'
    else:
        testsUrl = masterUrl+'/api/tests/'
    # get /tests/
    #resp = requests.get( testsUrl )
    #logger.info( 'testsUrl status_code %d', resp.status_code )
    #logger.info( '/api/tests/ json %s', resp.json() )

    # set params for tests
    nWorkers = args.nWorkers
    startTimeLimit = 30
    susTime = args.susTime
    usersPerWorker = args.usersPerWorker
    rampUpRate = args.rampUpRate
    if newApi:
        reqParams = { "url": args.victimHostUrl,
            "num-workers": str(nWorkers),
            "duration": str(susTime), 
            "users-per-worker": str(usersPerWorker),
            "reqMsprMean": str(args.reqMsprMean),
            "ramp-up-rate": str(rampUpRate)
        }
        if args.altTargetHostUrl:
            reqParams["alt-target-url"] = args.altTargetHostUrl
        if args.targetUris:
            reqParams["target-uris" ] = args.targetUris
        if args.regions:
            regionsDict = {'regions': args.regions}
            filterArg = json.dumps( regionsDict )
            # this code could become trickier if other filter args are supported
            reqParams['filter'] = regionsDict
            #reqParams['filter'] = filterArg
    else:
        reqParams = [args.victimHostUrl, "<MasterHostUnspecified>",
            "--authToken", args.authToken, "--nWorkers", str(nWorkers),
            "--susTime", str(susTime), "--usersPerWorker", str(usersPerWorker),
            "--reqMsprMean", str(args.reqMsprMean),
            "--rampUpRate", str(rampUpRate), "--startTimeLimit", str(startTimeLimit)
            ]
        if args.altTargetHostUrl:
            reqParams.append( '--altTargetHostUrl' )
            reqParams.append( args.altTargetHostUrl )
        if args.targetUris:
            reqParams.append( '--targetUris' )
            for uri in args.targetUris:
                reqParams.append( uri )
        if args.regions:
            regionsDict = {'regions': args.regions}
            filterArg = json.dumps( regionsDict )
            # this code could become trickier if other filter args are supported
            reqParams.append( '--filter' )
            reqParams.append( filterArg )
    logger.info( 'reqParams: %s', reqParams )    
    # start test
    testId = startTest( testsUrl, reqParams, args.authToken )
    logger.info( 'testId: %s', testId )

    # result dict from the service
    result = {}

    # poll the started tests
    while True:
        anyRunning = False
        statusUrl = testsUrl + testId
        logger.info( 'polling: %s', statusUrl )
        resp = requests.get( statusUrl, headers=ncscReqHeaders(args.authToken) )
        if resp.status_code != 200:
            logger.warning( 'poll status_code %d', resp.status_code )
        else:
            respJson = resp.json()
            result = respJson
            logger.info( 'poll json state: %s', respJson['state'] )
            if respJson.get( 'stderr' ):
                logger.info( 'poll json stderr: %s',
                    '\n'.join( respJson['stderr'].splitlines()[-5:] ) )
            else:
                logger.warning( 'no stderr object in returned json' )
            anyRunning = anyRunning or respJson['state'] in ['launching', 'running' ]
            #if respJson['state'] == 'stopped':
            #    break
        if not anyRunning:
            break
        time.sleep( 5 )

    # check result
    xmlOk = False
    gotStdout = False
    if not result:
        print( '>>NO result for', testId )
    else:
        if result.get('stdout'):
            gotStdout = True
            print('>>stdout from', testId)
            print( result['stdout'] )
        else:
            print('>>NO stdout from', testId)

    if gotStdout:
        dataUrlPrefix = testsUrl + testId
        if args.altTargetHostUrl:
            try:
                downloadDataFile( dataUrlPrefix + '/ltStats_a.html', dataDirPath )
            except Exception as exc:
                logger.warning( 'exception (%s) downloading; %s', type(exc), exc )
            try:
                downloadDataFile( dataUrlPrefix + '/ltStats_b.html', dataDirPath )
            except Exception as exc:
                logger.warning( 'exception (%s) downloading; %s', type(exc), exc )
        else:
            try:
                downloadDataFile( dataUrlPrefix + '/ltStats.html', dataDirPath )
            except Exception as exc:
                logger.warning( 'exception (%s) downloading; %s', type(exc), exc )
        try:
            downloadDataFile( dataUrlPrefix + '/locustStats.jlog', dataDirPath )
        except Exception as exc:
            logger.warning( 'exception (%s) downloading; %s', type(exc), exc )
        #try:
        #    downloadDataFile( dataUrlPrefix + '/integratedPerf.png', dataDirPath )
        #except Exception as exc:
        #    logger.warning( 'exception (%s) downloading; %s', type(exc), exc )
        for partialUrl in [
            'testResults.xml',
            'countryData.png',
            'durationHistogram.png',
            'durationHistogramLoaded.png',
            'integratedPerf.png',
            'msprScatter1.png',
            'nWorkers.png',
            'rps.png',
            'simulatedUsers.png'
            ]:
            downloadDataFileNoExc( dataUrlPrefix + '/' + partialUrl, dataDirPath )
        # move the xml report into place and check it for errors and failures
        if os.path.isfile( dataDirPath + '/testResults.xml' ):
            junitResultDirPath = dataDirPath + '/test-results/loadtest'
            junitResultFilePath = junitResultDirPath + '/results.xml'
            os.makedirs( junitResultDirPath, exist_ok=True )
            shutil.move( dataDirPath + '/testResults.xml', junitResultFilePath )
            with open( junitResultFilePath, encoding='utf8' ) as inFile:
                xml = inFile.read()
            if '<testcase' in xml and '<error' not in xml and '<failure' not in xml:
                xmlOk = True

    # save detailed outputs, if requested
    if args.jsonOut:
        argsToSave = vars(args).copy()
        del argsToSave['authToken']
        toSave = { 'args': argsToSave, 'result': result }
        jsonOutFilePath = os.path.expanduser( os.path.expandvars( args.jsonOut ) )
        with open( jsonOutFilePath, 'w') as outFile:
            json.dump( toSave, outFile, indent=2 )
            #json.dump( toSave, outFile, default=str, indent=2, skipkeys=True )
    sys.exit( not xmlOk )

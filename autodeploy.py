# Copyright (c) 2016 Amazon Web Services, Inc.

import boto3
import json
import logging
import datetime

ssm = boto3.client('ssm')
inspector = boto3.client('inspector')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# quick function to handle datetime serialization problems
enco = (
    lambda obj: obj.isoformat()
    if isinstance(obj, (datetime.datetime, datetime.date))
    else None
)

def lambda_handler(event, context):

    logger.debug('Raw Lambda event:')
    logger.debug(event)

    # check to ensure that this is an EC2 state change message
    eventType = event['detail-type']
    if eventType != 'EC2 Instance State-change Notification':
        logger.info(f'Not an EC2 state change notification, exiting: {eventType}')
        return 1

    # check to ensure that the new state is "running"
    newState = event['detail']['state']
    if newState != 'running':
        logger.info(f'Not an EC2 state change notification, exiting: {newState}')
        return 1

    # get the instance ID
    instanceId = event['detail']['instance-id']
    logger.info(f'Instance ID: {instanceId}')

    # query SSM for information about this instance
    filterList = [ { 'key': 'InstanceIds', 'valueSet': [ instanceId ] } ]
    response = ssm.describe_instance_information( InstanceInformationFilterList = filterList, MaxResults = 50 )
    logger.debug('SSM DescribeInstanceInformation response:')
    logger.debug(response)

    # ensure that the SSM agent is running on the instance
    if len(response) == 0:
        logger.info('SSM agent is not running on the target instance, exiting')
        return 1

    # get SSM metadata about the instance
    # assumption: len(InstanceInformationList) == 1 --> not explicitly checking
    instanceInfo = response['InstanceInformationList'][0]
    logger.debug('Instance information:')
    logger.debug(instanceInfo)
    pingStatus = instanceInfo['PingStatus']
    logger.info(f'SSM status of instance: {pingStatus}')
    lastPingTime = instanceInfo['LastPingDateTime']
    logger.debug('SSM last contact:')
    logger.debug(lastPingTime)
    agentVersion = instanceInfo['AgentVersion']
    logger.debug(f'SSM agent version: {agentVersion}')
    platformType = instanceInfo['PlatformType']
    logger.info(f'OS type: {platformType}')
    osName = instanceInfo['PlatformName']
    logger.info(f'OS name: {osName}')
    osVersion = instanceInfo['PlatformVersion']
    logger.info(f'OS version: {osVersion}')

    # Terminate if SSM agent is offline
    if pingStatus != 'Online':
        logger.info(
            f'SSM agent for this instance is not online, exiting: {pingStatus}'
        )

        return 1

    # This script only supports agent installation on Linux
    if platformType != "Linux":
        logger.info(f'Skipping non-Linux platform: {platformType}')
        return 1

    # set the command to deploy the inspector agent (note that curl and bash are required)
    commandLine = "cd /tmp; curl -O https://d1wk0tztpsntt1.cloudfront.net/linux/latest/install; bash /tmp/install"
    logger.info(f'Command line to execute: {commandLine}')

    # Run the command with SSM
    response = ssm.send_command(
        InstanceIds = [ instanceId ],
        DocumentName = 'AWS-RunShellScript',
        Comment = 'Lambda function performing Inspector agent installation',
        Parameters = { 'commands': [ commandLine ] }
        )

    logger.info('SSM send-command response:')
    logger.info(response)

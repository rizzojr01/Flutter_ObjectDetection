import time
import json
from datetime import datetime
from typing import Any, Dict


def format_detection_result(detected_object: str) -> Dict[str, Any]:
    """
    Format detection result into a dictionary.

    Parameters:
    - detected_object (str): The name of the detected object.

    Returns:
    Dict[str, Any]: Dictionary containing formatted detection result.
    """
    current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    data_to_push = {
        "id": current_datetime,
        "object_name": detected_object,
    }
    data = json.dumps(data_to_push)

    record = {"Data": data.encode("utf-8"), "PartitionKey": "nyu"}
    return record


def put_record_to_kinesis(
    kinesis_client: Any, record: Dict[str, Any], AWS_DATA_STREAM_NAME: str
) -> dict:
    """
    Put a record to the specified Kinesis data stream.

    Parameters:
    - kinesis_client (Any): The Kinesis client for making AWS Kinesis service requests.
    - record (Dict[str, Any]): The record to be sent to the data stream.
    - AWS_DATA_STREAM_NAME (str): The name of the AWS Kinesis data stream.

    Returns:
    dict: The response from the Kinesis service.

    Note:
    This function also prints the payload sent to the AWS data stream.
    """
    response = kinesis_client.put_records(
        Records=[record], StreamName=AWS_DATA_STREAM_NAME
    )

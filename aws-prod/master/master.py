from flask import Flask, request, jsonify
from flask_cors import CORS  # Import CORS
import time
import random
import os
import threading
import requests

import os
import json
import uuid
from config import DATASET_PATH
from dataset_util import download_dataset
from logger_util import logger
from redis_util import create_redis_client,save_subtasks_to_redis,update_subtask
from task_handler import create_subtasks,start_result_collector,consume_results
from kafka_util import KafkaSingleton,send_to_kafka
from datetime import datetime

redis_client = create_redis_client()


app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

@app.route("/")
def home():
    """Home route for the API."""
    return jsonify({
        "message": "Distributed ML System API",
        "status": "running",
        "endpoints": [
            "/execute_training",
            "/health",
            "/create_session",
            "/download_data/<session_id>",
            "/check_status/<session_id>/<job_id>",
            "/train/<session_id>"
        ]
    })

@app.route("/health", methods=["POST"])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "timestamp": time.time()
    })

@app.route("/create_session", methods=["POST"])
def create_session():
    """Creates a new user session and stores it in Redis."""
    session_id = str(uuid.uuid4())
    redis_client.sadd("active_sessions", session_id)  # Add to active sessions
    return jsonify({"message": "Session created", "session_id": session_id}), 201

@app.route('/download_data/<session_id>', methods=['POST'])
def download_data(session_id):

    # Validate session ID
    if not redis_client.sismember("active_sessions", session_id):
        return jsonify({"error": "Invalid session ID"}), 404

    data = request.get_json()
    # Validate dataset parameters
    url = data.get("dataset_url")
    name = data.get("dataset_name")
    source_type = data.get("dataset_type")

    if not url or not name or not source_type:
        return jsonify({"error": "Missing dataset parameters"}), 400

    dataset_path = os.path.join(DATASET_PATH, name)

    # Download the dataset synchronously
    success, message = download_dataset(url, source_type, dataset_path)

    if success:
        return jsonify({"message": message}), 200
    else:
        return jsonify({"error": message}), 500

# @app.route('/check_status/<session_id>/<job_id>', methods=['GET'])
# def check_status(session_id):
#     """Returns the number of pending tasks for a session."""
#     if not redis_client.sismember("active_sessions", session_id):
#         return jsonify({"error": "Invalid session ID"}), 404
#
#     pending_tasks = int(redis_client.get(f"session:{session_id}:tasks_pending") or 0)
#     return jsonify({"session_id": session_id, "tasks_pending": pending_tasks})
@app.route('/check_status/<session_id>/<job_id>', methods=['GET'])
def check_status(session_id, job_id):
    """Returns the number of pending tasks for a session, job status, and job results if completed."""

    # Check if the session is valid
    if not redis_client.sismember("active_sessions", session_id):
        return jsonify({"error": "Invalid session ID"}), 404

    # Get pending tasks for the session
    pending_tasks = int(redis_client.get(f"active_sessions:{session_id}:jobs:{job_id}:tasks_pending") or 0)

    # Check job status
    # job_status = redis_client.get(f"jobs:{job_id}:status")
    job_status = redis_client.get(f"jobs:{job_id}:status")
    logger.info(job_status)
    # if not job_status:
    #     return jsonify({"error": f"Job {job_id} not found."}), 404

    # job_status = job_status # Decode from bytes to string

    # Get the total number of subtasks for the job
    subtask_keys = redis_client.keys(f"active_sessions:{session_id}:jobs:{job_id}:subtasks:{job_id}-subtask-*")
    total_subtasks = len(subtask_keys)

    # If the job is completed, fetch the job results
    if job_status == "completed":
        job_result = redis_client.get(f"jobs:{job_id}:result")
        if not job_result:
            return jsonify({"error": "Job result not found."}), 404

        job_result = json.loads(job_result)  # Decode and parse the result from JSON

        return jsonify({
            "session_id": session_id,
            "tasks_pending": pending_tasks,
            "job_id": job_id,
            "job_status": job_status,
            "job_result": job_result,  # Include job results in the response
            "total_subtasks": total_subtasks  # Total subtasks for the status bar
        })

    # If the job is not completed, return job status and pending tasks
    return jsonify({
        "session_id": session_id,
        "tasks_pending": pending_tasks,
        "job_id": job_id,
        "job_status": job_status,
        "total_subtasks": total_subtasks  # Total subtasks for the status bar
    })


@app.route('/train/<session_id>', methods=['POST'])
def train(session_id):

    producer = KafkaSingleton.get_producer()

    if not redis_client.sismember("active_sessions", session_id):
        return jsonify({"error": "Invalid session ID"}), 404
    #

    model_config = request.get_json()


    # # job_id = model_config.get('job_id')
    # # session_id = model_config['session_id']
    dataset_id = model_config.get('dataset_id')
    dataset_path = f"/datasets/{dataset_id}/{dataset_id}.csv"  # On AWS Comment
    # dataset_path = f"/mnt/datasets/{dataset_id}.csv" # ON AWS uncomment
    if not os.path.exists(dataset_path):
        return jsonify({'error': f'Dataset {dataset_id} not found, Please Use download_data function'}), 404
    # model_details = model_config['model_details']
    # data_config = model_config.get('data_config', {})
    logger.info(model_config)
    subtasks = create_subtasks(model_config)
    subtask_list = [task['subtask_id'] for task in subtasks]
    logger.info(subtasks)
    redis_status = save_subtasks_to_redis(subtasks,redis_client)
    logger.info(redis_status)
    send_to_kafka(subtasks,producer)

    listener_thread = threading.Thread(target=consume_results, args=(subtask_list,session_id), daemon=True)
    listener_thread.start()
    logger.info("Result collector thread started here...")




    return jsonify({"All good": "final test"})


@app.route('/job_results/<session_id>/<job_id>', methods=['GET'])
def job_results(session_id, job_id):
    """Get results for a specific job"""
    # Validate session ID
    if not redis_client.sismember("active_sessions", session_id):
        return jsonify({"error": "Invalid session ID"}), 404

    # Check if job belongs to session
    if not redis_client.sismember(f"session:{session_id}:jobs", job_id):
        return jsonify({"error": "Job not found for this session"}), 404

    # Get job status
    job_status = redis_client.get(f"job:{job_id}:status")
    if not job_status:
        return jsonify({"error": "Job not found"}), 404

    job_status = job_status.decode('utf-8')

    # If job is still processing, return status and completion percentage
    if job_status != "completed":
        completion = redis_client.get(f"job:{job_id}:completion") or b'0'
        return jsonify({
            "job_id": job_id,
            "status": job_status,
            "completion_percentage": float(completion)
        }), 200

    # If job is completed, return results
    job_result = redis_client.get(f"job:{job_id}:result")
    if job_result:
        return jsonify(json.loads(job_result)), 200
    else:
        return jsonify({
            "job_id": job_id,
            "status": "completed",
            "error": "Results not found"
        }), 404


if __name__ == "__main__":
    logger.info("Starting Flask server...")

    # logger.info("Result Collector started...")
    app.run(debug=True, host="0.0.0.0", port=5001)
    # start_result_collector()
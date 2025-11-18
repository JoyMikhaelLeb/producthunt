#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Jun 24 15:05:05 2024

@author: joy
"""


import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from pydantic import BaseModel
from typing import Optional
import datetime
from datetime import timedelta, UTC
import random

if not firebase_admin._apps:
    cred = credentials.Certificate("spherical-list-284723-216944ab15f1.json")
    default_app = firebase_admin.initialize_app(cred)

db = firestore.client()




class TaskClass(BaseModel):
    # id: str # p1_22032021_235312_about_hexagonppm-sudamerica
    category: str  # about, insights, TEST, founders, ppl (about of person)
    # worker_type: str  # regular, premium, sales
    t_priority: int  # 1, 2, 3
    client: str  # dr, TEST
    target: str  # hexagonppm-sudamerica
    request_id: str  # p2_26032021_011440_founder_gvgvgvg
    ref: Optional[str] = ""  # some reference
    status: Optional[str] = "in_queue"
    created: Optional[datetime.datetime] = ""
    adhoc: bool = True
    required_labels: list


class Request(BaseModel):
    # id: str # p1_22032021_235312_about_hexagonppm-sudamerica
    category: str  # about, ppl, insights, TEST, founder, profile, search, distribution, profile-info
    status: str
    r_priority: int  # 1, 2, 3
    #client: str  # dr, TEST
    target: Optional[str] = ""  # hexagonppm-sudamerica
    ref: Optional[str] = ""  # some reference
    created: Optional[datetime.datetime] = ""
    
    
def create_task(taskcreated: TaskClass):
    """Create a task and store it in db"""
    now = datetime.datetime.now(UTC)
    date_str = now.strftime("%d%m%Y")

    task_dict = taskcreated.dict()
    # print("task_dict:", task_dict)
    task_dict.update(
        {
            "id": f'p{str(task_dict["t_priority"])}_{date_str}_{gen_random_digit_str(6)}-{gen_random_digit_str(6)}_{task_dict["category"]}_{task_dict["target"]}'
        }
    )
   
    task_dict.update({"updated": now, "created": now})

    # print("task_dict2:", task_dict)
    # create the Task in firestore
    
    db.collection("automation").document("current").collection("requests").document(
        task_dict["request_id"]
    ).collection("tasks").document(task_dict["id"]).set(task_dict)
    #db.collection("automation").document("current").collection("requests").document(task_dict["request_id"]).update({"updated": datetime.datetime.now(UTC)})

    # print(
    #     f"[LOG] Task of id {task_dict['id']} with request id {task_dict['request_id']} created."
    # )

    return task_dict

def gen_random_digit_str(length: int):
    str1 = str()
    for i in range(length):
        str1 += str(random.randint(0, 9))
    return str1



def create_request(request: Request):
    """Create a request and store it in db"""
    now = datetime.datetime.now(UTC)
    date_str = now.strftime("%d%m%Y")

    request_dict = request.dict()
    request_dict.update(
        {
            "id": str(
                f'r{str(request_dict["r_priority"])}_{date_str}_{request_dict["category"]}_{str(request_dict["r_priority"])}'
            )
        }
    )

    request_dict.update({"created": now})

    request_dict.update({"status": request_dict["status"]})
    request_dict.update({"updated": now})
   
    print("request_dict:", request_dict)
    # create the request in firestore

    db.collection("automation").document("current").collection("requests").document(
        request_dict["id"]
    ).set(request_dict, merge=True)

    return request_dict
    
def task_exists(doc_id, category):
    # Check in the current request's tasks
    request_id = f"r1_{datetime.datetime.now(UTC).date().day:02}{datetime.datetime.now(UTC).date().month:02}{datetime.datetime.now(UTC).date().year}_adhoc_1"
    
    # Get all tasks in the current request
    tasks = (db.collection("automation")
             .document("current")
             .collection("requests")
             .document(request_id)
             .collection("tasks")
             .where("target", "==", doc_id)
             .where("category", "==", category)
             .get())
    
    return len(tasks) > 0

def create_about_task(doc_id):
    # First check if task already exists
    if task_exists(doc_id, "about"):
        print(f"Task for {doc_id} already exists")
        return "task already exists"

    now = datetime.datetime.now(UTC)
    date_str = now.strftime("%d%m%Y")

    request_id = f"r1_{datetime.datetime.now(UTC).date().day:02}{datetime.datetime.now(UTC).date().month:02}{datetime.datetime.now(UTC).date().year}_adhoc_1"
    if (db.collection("automation")
        .document("current")
        .collection("requests")
        .document(request_id)
        .get()
        .to_dict() is None
        ):
        request = Request(
            category="adhoc",
            status="in_queue",
            r_priority=1,
        )
        request_id = create_request(request)
        request_id = request_id["id"]
        
    task_alpha = TaskClass(
        category="about",
        t_priority=3,
        client="TEST777",
        request_id=request_id,
        status="in_queue",
        ref="",
        target=doc_id,
        required_labels=['general','later'],
    )
    task_dict = create_task(task_alpha)
    return "request made"
    
    
def create_ppl_task(doc_id):
    # First check if task already exists
    if task_exists(doc_id, "about"):
        print(f"Task for {doc_id} already exists")
        return "task already exists"

    now = datetime.datetime.now(UTC)
    date_str = now.strftime("%d%m%Y")

    request_id = f"r1_{datetime.datetime.now(UTC).date().day:02}{datetime.datetime.now(UTC).date().month:02}{datetime.datetime.now(UTC).date().year}_adhoc_1"
    if (db.collection("automation")
        .document("current")
        .collection("requests")
        .document(request_id)
        .get()
        .to_dict() is None
        ):
        request = Request(
            category="adhoc",
            status="in_queue",
            r_priority=1,
        )
        request_id = create_request(request)
        request_id = request_id["id"]
        
    task_ppl = TaskClass(
        category="ppl",
        t_priority=3,
        client="TEST777",
        request_id=request_id,
        status="in_queue",
        ref="",
        target=doc_id,
        required_labels=['ppl','special'],
    )
    task_dict = create_task(task_ppl)
    return "request made"
def create_numerical_task(doc_id):
    # First check if task already exists
    if task_exists(doc_id, "numerical_about"):
        print(f"Task for {doc_id} already exists")
        return "task already exists"

    now = datetime.datetime.now(UTC)
    date_str = now.strftime("%d%m%Y")

    request_id = f"r1_{datetime.datetime.now(UTC).date().day:02}{datetime.datetime.now(UTC).date().month:02}{datetime.datetime.now(UTC).date().year}_adhoc_1"
    if (db.collection("automation")
        .document("current")
        .collection("requests")
        .document(request_id)
        .get()
        .to_dict() is None
        ):
        request = Request(
            category="adhoc",
            status="in_queue",
            r_priority=1,
        )
        request_id = create_request(request)
        request_id = request_id["id"]
        
    task_numerical = TaskClass(
        category="numerical_about",
        t_priority=3,
        client="TEST777",
        request_id=request_id,
        status="in_queue",
        ref="",
        target=doc_id,
        required_labels=['general','special'],
    )
    task_dict = create_task(task_numerical)
    return "request made"

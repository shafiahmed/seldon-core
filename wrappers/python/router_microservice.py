from proto import prediction_pb2, prediction_pb2_grpc
from microservice import extract_message, sanity_check_request, rest_datadef_to_array, \
    array_to_rest_datadef, grpc_datadef_to_array, array_to_grpc_datadef, \
    SeldonMicroserviceException
import grpc
from concurrent import futures

from flask import jsonify, Flask
import numpy as np
import os

PRED_UNIT_ID = os.environ.get("PREDICTIVE_UNIT_ID")

# ---------------------------
# Interaction with user router
# ---------------------------

def route(user_router,features,feature_names):
    return user_router.route(features,feature_names)

def send_feedback(user_router,features,feature_names,routing,reward,truth):
    return user_router.send_feedback(features,feature_names,routing,reward,truth)

# ----------------------------
# REST
# ----------------------------

def get_rest_microservice(user_router):

    app = Flask(__name__)

    @app.errorhandler(SeldonMicroserviceException)
    def handle_invalid_usage(error):
        response = jsonify(error.to_dict())
        response.status_code = 400
        return response


    @app.route("/route",methods=["GET","POST"])
    def Route():
        request = extract_message()
        sanity_check_request(request)
        
        datadef = request.get("data")
        features = rest_datadef_to_array(datadef)

        routing = np.array([[route(user_router,features,datadef.get("names"))]])
        # TODO: check that predictions is 2 dimensional
        class_names = []

        data = array_to_rest_datadef(routing, class_names, datadef)

        return jsonify({"data":data})

    @app.route("/send-feedback",methods=["GET","POST"])
    def SendFeedback():
        feedback = extract_message()
        
        datadef_request = feedback.get("request").get("data")
        features = rest_datadef_to_array(datadef)
        
        truth = rest_datadef_to_array(feedback.get("truth"))
        reward = feedback.get("reward")
        routing = feedback.get("response").get("meta").get("routing").get(PRED_UNIT_ID)

        send_feedback(user_router,features,datadef_request.get("names"),routing,reward,truth)
        return jsonify({})

    return app



# ----------------------------
# GRPC
# ----------------------------

class SeldonRouterGRPC(object):
    def __init__(self,user_model):
        self.user_model = user_model

    def Route(self,request,context):
        datadef = request.data
        features = grpc_datadef_to_array(datadef)

        routing = np.array([[route(self.user_model,features,datadef.names)]])
        #TODO: check that predictions is 2 dimensional
        class_names = []

        data = array_to_grpc_datadef(routing, class_names, request.data.WhichOneof("data_oneof"))
        return prediction_pb2.SeldonMessage(data=data)

    def SendFeedback(self,feedback,context):
        datadef_request = feedback.request.data
        features = grpc_datadef_to_array(datadef_request)
        
        truth = grpc_datadef_to_array(feedback.truth)
        reward = feedback.reward
        routing = feedback.response.meta.routing.get(PRED_UNIT_ID)
        
        send_feedback(self.user_model,features,datadef_request.names,routing,reward,truth)

        return prediction_pb2.SeldonMessage()
    
def get_grpc_server(user_model):
    seldon_router = SeldonRouterGRPC(user_model)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    prediction_pb2_grpc.add_RouterServicer_to_server(seldon_router, server)

    return server

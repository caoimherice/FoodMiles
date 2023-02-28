import os
import boto3
import datetime
from flask import Flask, jsonify, make_response, request

app = Flask(__name__)


dynamodb_client = boto3.client('dynamodb')

if os.environ.get('IS_OFFLINE'):
    dynamodb_client = boto3.client(
        'dynamodb', region_name='localhost', endpoint_url='http://localhost:8000'
    )


USERS_TABLE = os.environ['USERS_TABLE']
ITEM_TABLE = os.environ['ITEM_TABLE']
SHOPPING_LIST_TABLE = os.environ['SHOPPING_LIST_TABLE']
SAVED_LIST_TABLE = os.environ['SAVED_LIST_TABLE']
ROUTE_TABLE = os.environ['ROUTE_TABLE']


@app.route('/users/<string:user_id>')
def get_user(user_id):
    result = dynamodb_client.get_item(
        TableName=USERS_TABLE, Key={'userId': {'S': user_id}}
    )
    item = result.get('Item')
    if not item:
        return jsonify({'error': 'Could not find user with provided "userId"'}), 404

    return jsonify(
        {'userId': item.get('userId').get('S'), 'name': item.get('name').get('S')}
    )


@app.route('/users', methods=['POST'])
def create_user():
    user_id = request.json.get('userId')
    name = request.json.get('name')
    if not user_id or not name:
        return jsonify({'error': 'Please provide both "userId" and "name"'}), 400

    dynamodb_client.put_item(
        TableName=USERS_TABLE, Item={'userId': {'S': user_id}, 'name': {'S': name}}
    )

    return jsonify({'userId': user_id, 'name': name})


@app.route('/food/item', methods=['POST'])
def create_item():
    name = request.json.get('name')
    origin = request.json.get('origin')
    miles = request.json.get('miles')
    if not name or not origin or not miles:
        return jsonify({'error': 'Please provide both "name" and "origin" and "miles"'}), 400

    dynamodb_client.put_item(
        TableName=ITEM_TABLE, Item={'name': {'S': name}, 'origin': {'S': origin}, 'miles': {'S': miles}}
    )

    return jsonify({'name': name, 'origin': origin, 'miles': miles})


@app.route('/food/item/<string:name>/<string:origin>')
def get_item(name, origin):
    result = dynamodb_client.get_item(
        TableName=ITEM_TABLE, Key={'name': {'S': name}, 'origin': {'S': origin}}
    )
    item = result.get('Item')
    if not item:
        return jsonify({'error': 'Could not find food item with provided "name and origin"'}), 404

    return jsonify(
        {'name': item.get('name').get('S'), 'origin': item.get('origin').get('S'), 'miles': item.get('miles').get('S')}
    )


@app.route('/shoppingList/item', methods=['POST'])
def add_item():
    userId = request.json.get('userId')
    name = request.json.get('name')
    origin = request.json.get('origin')
    itemId = name + ',' + origin
    if not name or not origin or not userId:
        return jsonify({'error': 'Please provide both "name" and "origin" and "userId"'}), 400

    dynamodb_client.put_item(
        TableName=SHOPPING_LIST_TABLE, Item={'userId': {'S': userId}, 'itemId': {'S': itemId}}
    )

    return jsonify({'userId': userId, 'itemId': itemId})


@app.route('/shoppingList/item/<string:userId>')
def get_list(userId):
    result = dynamodb_client.query(
        TableName=SHOPPING_LIST_TABLE,
        KeyConditionExpression='userId = :userId',
        ExpressionAttributeValues={
            ':userId': {'S': userId}
        }
    )
    items = result.get("Items")
    return jsonify(items)


@app.route('/shoppingList/details/<string:userId>')
def get_list_details(userId):
    result = dynamodb_client.query(
        TableName=SHOPPING_LIST_TABLE,
        KeyConditionExpression='userId = :userId',
        ExpressionAttributeValues={
            ':userId': {'S': userId}
        }
    )
    total_miles = 0
    items = result.get("Items")
    # iterate through each item in the shopping list and retrieve the item details using get_item()
    for item in items:
        name = item.get('itemId').get('S').split(',')[0]
        origin = item.get('itemId').get('S').split(',')[1]
        item_result = dynamodb_client.get_item(
            TableName=ITEM_TABLE, Key={'name': {'S': name}, 'origin': {'S': origin}}
        )
        item_details = item_result.get('Item')
        if not item_details:
            return jsonify({'error': f'Could not find food item with name "{name}" and origin "{origin}"'}), 404
        total_miles += int(item_details.get('miles').get('S'))
        item['itemDetails'] = {
            'name': item_details.get('name').get('S'),
            'origin': item_details.get('origin').get('S'),
            'miles': item_details.get('miles').get('S')
        }
    return jsonify(items, {'total_miles': total_miles})


@app.route('/savedList/list', methods=['POST'])
def add_list():
    userId = request.json.get('userId')
    if not userId:
        return jsonify({'error': 'Please provide "userId"'}), 400
        # Get the list of items from the request body
    items = request.json.get('items')
    if not items:
        return jsonify({'error': 'Please provide "items"'}), 400
    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # Create a new item to be added to the database
    new_item = {
        'userId': {'S': userId},
        'createdAt': {'S': current_time},
        'items': {'L': []}
    }
    # Add each item to the "items" list
    for item in items:
        item_details = {
            'name': {'S': item.get('itemDetails').get('name')},
            'origin': {'S': item.get('itemDetails').get('origin')},
            'miles': {'S': item.get('itemDetails').get('miles')}
        }
        new_item['items']['L'].append({'M': {'itemDetails': {'M': item_details}}})
    dynamodb_client.put_item(
        # TableName=SAVED_LIST_TABLE, Item={'userId': {'S': userId}, 'createdAt': {'S': current_time}}
        TableName=SAVED_LIST_TABLE, Item=new_item
    )

    # Return a response with the saved user ID, creation time, and items
    # response = {'userId': userId, 'createdAt': current_time, 'items': items}
    # return jsonify(response)
    # return jsonify({'userId': userId, 'createdAt': current_time})
    return jsonify({'message': 'Items saved successfully'})


@app.route('/savedList/list/<string:userId>', methods=['GET'])
def get_saved_list(userId):
    result = dynamodb_client.query(
        TableName=SAVED_LIST_TABLE,
        KeyConditionExpression='userId = :userId',
        ExpressionAttributeValues={
            ':userId': {'S': userId}
        }
    )
    items = []
    for item in result['Items']:
        items_list = item['items']['L']
        new_item = {'createdAt': item['createdAt']['S']}
        # items.append({'createdAt': item['createdAt']['S']})
        new_list = []
        for i in items_list:
            new_list.append({
                'itemDetails': {
                    'name': i['M']['itemDetails']['M']['name']['S'],
                    'origin': i['M']['itemDetails']['M']['origin']['S'],
                    'miles': i['M']['itemDetails']['M']['miles']['S']
                }
            })
            new_item.update({'items_list': new_list})
        items.append(new_item)
    return jsonify(items)


@app.route('/route', methods=['POST'])
def add_route():
    origin = request.json.get('origin')
    destination = request.json.get('destination')
    origin_lat_lng = request.json.get('origin_lat_lng')
    destination_lat_lng = request.json.get('destination_lat_lng')
    lead_time = request.json.get('lead_time')
    transport_mode = request.json.get('transport_mode')
    distance = request.json.get('distance')
    emissions = request.json.get('emissions')
    coordinates = []
    for item in request.json.get('coordinates'):
        coordinates.append({'L': [{'N': str(item[0])}, {'N': str(item[1])}]})
    if not origin or not destination or not origin_lat_lng or not destination_lat_lng or not lead_time or not transport_mode or not distance or not emissions or not coordinates:
        return jsonify({'error': 'Please provide all required attributes'}), 400
    dynamodb_client.put_item(
        TableName=ROUTE_TABLE, Item={'origin': {'S': origin}, 'destination': {'S': destination}, 'origin_lat_lng': {'S': origin_lat_lng}, 'destination_lat_lng': {'S': destination_lat_lng}, 'lead_time': {'S': lead_time}, 'distance': {'S': distance}, 'emissions': {'S': emissions}, 'coordinates': {'L': coordinates}}
    )
    return jsonify({'message': 'Route added successfully'})


@app.route('/route/<string:origin>/<string:destination>', methods=['GET'])
def get_route(origin, destination):
    result = dynamodb_client.get_item(
        TableName=ROUTE_TABLE, Key={'origin': {'S': origin}, 'destination': {'S': destination}}
    )
    item = result.get('Item')
    if not item:
        return jsonify({'error': 'Could not find route with provided "origin" and "destination"'}), 404

    coordinates = []
    for coord in item.get('coordinates').get('L'):
        coordinates.append([float(coord['L'][0]['N']), float(coord['L'][1]['N'])])
    return jsonify(
        {'origin': item.get('origin').get('S'), 'destination': item.get('destination').get('S'), 'origin_lat_lng': item.get('origin_lat_lng').get('S'), 'destination_lat_lng': item.get('destination_lat_lng').get('S'), 'lead_time': item.get('lead_time').get('S'), 'distance': item.get('distance').get('S'), 'emissions': item.get('emissions').get('S'), 'coordinates': coordinates}
    )


    # items = []
    # items_list = []
    # for item in result['Items']:
    #     items_list = item['items']['L']
    #     new_item = [{'createdAt': item['createdAt']['S']}]
    #     # items.append({'createdAt': item['createdAt']['S']})
    #     for i in items_list:
    #         new_item.append({
    #             'itemDetails': {
    #                 'name': i['M']['itemDetails']['M']['name']['S'],
    #                 'origin': i['M']['itemDetails']['M']['origin']['S'],
    #                 'miles': i['M']['itemDetails']['M']['miles']['S']
    #             }
    #         })
    #         items.append(new_item)
    # return jsonify(items)

    # items = result.get("Items")
    # # iterate through each item in the shopping list and retrieve the item details using get_item()
    # for item in items:
    #     name = item.get('itemId').get('S').split(',')[0]
    #     origin = item.get('itemId').get('S').split(',')[1]
    #     item_result = dynamodb_client.get_item(
    #         TableName=ITEM_TABLE, Key={'name': {'S': name}, 'origin': {'S': origin}}
    #     )
    #     item_details = item_result.get('Item')
    #     if not item_details:
    #         return jsonify({'error': f'Could not find food item with name "{name}" and origin "{origin}"'}), 404
    #     item['itemDetails'] = {
    #         'name': item_details.get('name').get('S'),
    #         'origin': item_details.get('origin').get('S'),
    #         'miles': item_details.get('miles').get('S')
    #     }
    # return jsonify(items)

# @app.route('/savedList/<userId>', methods=['GET'])
# def get_saved_list(userId):
#     response = dynamodb_client.get_item(
#         TableName=SAVED_LIST_TABLE,
#         Key={'userId': {'S': userId}}
#     )
#
#     if 'Item' not in response:
#         return jsonify({'error': f'No saved list found for user ID {userId}'}), 404
#
#     saved_list = response['Item']
#     items = saved_list['items']['L']
#
#     item_details_list = []
#     for item in items:
#         item_details_list.append(item['M']['itemDetails']['M'])
#
#     result = {
#         'userId': saved_list['userId']['S'],
#         'createdAt': saved_list['createdAt']['S'],
#         'items': item_details_list
#     }
#
#     return jsonify(result)
@app.errorhandler(404)
def resource_not_found(e):
    return make_response(jsonify(error='Not found!'), 404)

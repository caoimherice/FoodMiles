import os
import boto3
import datetime
import asyncio
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


@app.route('/food/item', methods=['POST'])
def create_item():
    name = request.json.get('name')
    origin = request.json.get('origin')
    legs = request.json.get('legs')
    if not name or not origin or not legs:
        return jsonify({'error': 'Please provide both "name" and "origin" and "legs"'}), 400
    # This code converts each leg dictionary in the legs list into a map that contains origin and destination as keys
    # and the corresponding values as strings (S type). Then, it creates a new list legs_dynamodb that contains these
    # maps wrapped in M type. Finally, it passes this list to DynamoDB as the value of the legs attribute of the Item
    # dictionary.
    legs_dynamodb = [{'M': {'origin': {'S': leg['origin']}, 'destination': {'S': leg['destination']}}} for leg in legs]
    dynamodb_client.put_item(
        TableName=ITEM_TABLE, Item={'name': {'S': name}, 'origin': {'S': origin}, 'legs': {'L': legs_dynamodb}}
    )
    return jsonify({'name': name, 'origin': origin, 'legs': legs})


@app.route('/food/item/<string:name>/<string:origin>')
def get_item(name, origin):
    result = dynamodb_client.get_item(
        TableName=ITEM_TABLE, Key={'name': {'S': name}, 'origin': {'S': origin}}
    )
    item = result.get('Item')
    if not item:
        return jsonify({'error': 'Could not find food item with provided "name and origin"'}), 404
    legs_dynamodb = item['legs']['L']
    legs = [{'origin': leg['M']['origin']['S'], 'destination': leg['M']['destination']['S']} for leg in legs_dynamodb]
    return jsonify(
        {'name': item.get('name').get('S'), 'origin': item.get('origin').get('S'), 'legs': legs}
    )


@app.route('/shoppingList/item', methods=['POST'])
def add_item():
    userId = request.json.get('userId')
    name = str(request.json.get('name'))
    origin = str(request.json.get('origin'))
    itemId = name + ',' + origin
    if not name or not origin or not userId:
        return jsonify({'error': 'Please provide both "name" and "origin" and "userId"'}), 400
    dynamodb_client.put_item(
        TableName=SHOPPING_LIST_TABLE, Item={'userId': {'S': userId}, 'itemId': {'S': itemId}}
    )
    return jsonify({'userId': userId, 'itemId': itemId})


@app.route('/shoppingList/delete', methods=['DELETE'])
def delete_item():
    userId = request.json.get('userId')
    name = str(request.json.get('name'))
    origin = str(request.json.get('origin'))
    itemId = name + ',' + origin
    if not name or not origin or not userId:
        return jsonify({'error': 'Please provide both "name" and "origin" and "userId"'}), 400
    dynamodb_client.delete_item(
        TableName=SHOPPING_LIST_TABLE, Key={'userId': {'S': userId}, 'itemId': {'S': itemId}}
    )
    return jsonify({'message': 'Item deleted successfully'})


# @app.route('/shoppingList/item/<string:userId>')
# def get_list(userId):
#     result = dynamodb_client.query(
#         TableName=SHOPPING_LIST_TABLE,
#         KeyConditionExpression='userId = :userId',
#         ExpressionAttributeValues={
#             ':userId': {'S': userId}
#         }
#     )
#     items = result.get("Items")
#     return jsonify(items)


@app.route('/shoppingList/details/<string:userId>')
def get_list_details(userId):
    result = dynamodb_client.query(
        TableName=SHOPPING_LIST_TABLE,
        KeyConditionExpression='userId = :userId',
        ExpressionAttributeValues={
            ':userId': {'S': userId}
        }
    )
    total_distance = 0
    total_emissions = 0
    total_lead_time = 0
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
        legs_dynamodb = item_details['legs']['L']
        legs = [{'origin': leg['M']['origin']['S'], 'destination': leg['M']['destination']['S']} for leg in
                legs_dynamodb]
        distance = 0
        emissions = 0
        lead_time = 0
        for leg in legs:
            route_origin = leg.get('origin')
            route_destination = leg.get('destination')
            route_result = dynamodb_client.get_item(
                TableName=ROUTE_TABLE, Key={'origin': {'S': route_origin}, 'destination': {'S': route_destination}}
            )
            route = route_result.get('Item')
            if not route:
                return jsonify({'error': f'Could not find route with origin "{route_origin}" and destination "{route_destination}"'}), 404
            distance += int(route.get('distance').get('S'))
            emissions += int(route.get('emissions').get('S'))
            lead_time += int(route.get('lead_time').get('S'))
        item['itemDetails'] = {
            'name': name,
            'origin': origin,
            'distance': distance,
            'emissions': emissions,
            'lead_time': lead_time,
        }
        total_distance += distance
        total_emissions += emissions
        total_lead_time += lead_time
    return jsonify(items, {'total_distance': total_distance}, {'total_emissions': total_emissions},
                   {'total_lead_time': total_lead_time})


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
    # # Add each item to the "items" list
    for item in items:
        item_id = {
            'itemId': {'S': item.get('itemId').get('S')},
        }
        new_item['items']['L'].append({'M': item_id})
    dynamodb_client.put_item(
        # TableName=SAVED_LIST_TABLE, Item={'userId': {'S': userId}, 'createdAt': {'S': current_time}}
        TableName=SAVED_LIST_TABLE, Item=new_item
    )
    for item in items:
        item_id = item.get('itemId').get('S')
        dynamodb_client.delete_item(
            TableName=SHOPPING_LIST_TABLE,
            Key={
                'userId': {'S': userId},
                'itemId': {'S': item_id}
            }
        )

    # Return a response with the saved user ID, creation time, and items
    # response = {'userId': userId, 'createdAt': current_time, 'items': items}
    # return jsonify(response)
    # return jsonify({'userId': userId, 'createdAt': current_time})
    return jsonify({'message': 'Items saved successfully'})


@app.route('/savedList/list/<string:userId>', methods=['GET'])
# def get_saved_list(userId):
#     result = dynamodb_client.query(
#         TableName=SAVED_LIST_TABLE,
#         KeyConditionExpression='userId = :userId',
#         ExpressionAttributeValues={
#             ':userId': {'S': userId}
#         }
#     )
#     items = []
#     for item in result['Items']:
#         total_distance = 0
#         total_emissions = 0
#         total_lead_time = 0
#         items_list = item['items']['L']
#         new_item = {'createdAt': item['createdAt']['S']}
#         # items.append({'createdAt': item['createdAt']['S']})
#         new_list = []
#         for i in items_list:
#             name = i['M']['itemId']['S'].split(',')[0]
#             origin = i['M']['itemId']['S'].split(',')[1]
#             item_result = dynamodb_client.get_item(
#                 TableName=ITEM_TABLE, Key={'name': {'S': name}, 'origin': {'S': origin}}
#             )
#             item_details = item_result.get('Item')
#             if not item_details:
#                 return jsonify({'error': f'Could not find food item with name "{name}" and origin "{origin}"'}), 404
#             legs_dynamodb = item_details['legs']['L']
#             legs = [{'origin': leg['M']['origin']['S'], 'destination': leg['M']['destination']['S']} for leg in
#                     legs_dynamodb]
#             distance = 0
#             emissions = 0
#             lead_time = 0
#             for leg in legs:
#                 route_origin = leg.get('origin')
#                 route_destination = leg.get('destination')
#                 print('Start of get route function for: ', leg, 'for the item: ', i)
#                 route_result = dynamodb_client.get_item(
#                     TableName=ROUTE_TABLE, Key={'origin': {'S': route_origin}, 'destination': {'S': route_destination}}
#                 )
#                 print('Finish of get route function for: ', leg, 'for the item: ', i)
#                 route = route_result.get('Item')
#                 if not route:
#                     return jsonify({
#                                        'error': f'Could not find route with origin "{route_origin}" and destination "{route_destination}"'}), 404
#                 distance += round(int(route.get('distance').get('S'))/1000, 2)
#                 emissions += int(route.get('emissions').get('S'))
#                 lead_time += int(route.get('lead_time').get('S'))
#             new_list.append({
#                 'name': name,
#                 'origin': origin,
#                 'distance': distance,
#                 'emissions': emissions,
#                 'lead_time': lead_time,
#             })
#             total_distance += distance
#             total_emissions += emissions
#             total_lead_time += lead_time
#             new_item.update({'items_list': new_list})
#             new_item.update({'total_distance': total_distance})
#             new_item.update({'total_emissions': total_emissions})
#             new_item.update({'total_lead_time': total_lead_time})
#         items.append(new_item)
#     return jsonify(items)
async def get_saved_list(userId):
    print('Start of function')
    result = dynamodb_client.query(
        TableName=SAVED_LIST_TABLE,
        KeyConditionExpression='userId = :userId',
        ExpressionAttributeValues={
            ':userId': {'S': userId}
        }
    )
    print('Result of saved items call: ', result)
    saved_lists = []
    for saved_list in result['Items']:
        saved_items = saved_list['items']['L']

        print('Start of async get items')
        items = await asyncio.gather(*[create_list_item(item) for item in saved_items])
        print('Finish of async get items')

        total_distance = 0
        total_emissions = 0
        total_lead_time = 0

        for item in items:
            total_distance += item['distance']
            total_emissions += item['emissions']
            total_lead_time += item['lead_time']

        shopping_list = {
            'createdAt': saved_list['createdAt']['S'],
            'items_list': items,
            'total_distance': total_distance,
            'total_emissions': total_emissions,
            'total_lead_time': total_lead_time
        }

        saved_lists.append(shopping_list)

    print('Finish of function')
    return jsonify(saved_lists)


async def create_list_item(item):
    print('Start of get item function for: ', item)
    name = item['M']['itemId']['S'].split(',')[0]
    origin = item['M']['itemId']['S'].split(',')[1]
    print('Start of item query')
    result = dynamodb_client.get_item(
        TableName=ITEM_TABLE, Key={'name': {'S': name}, 'origin': {'S': origin}}
    )
    print('Finish of item query')
    saved_item = result['Item']
    if not saved_item:
        return jsonify({'error': f'Could not find food item with name "{name}" and origin "{origin}"'}), 404

    legs = saved_item['legs']['L']

    print('Start of async get legs')
    routes = await asyncio.gather(*[get_route_info(leg) for leg in legs])
    print('Finish of async get legs')

    distance = 0
    emissions = 0
    lead_time = 0

    for route in routes:
        distance += int(route['distance']['S'])
        emissions += int(route['emissions']['S'])
        lead_time += int(route['lead_time']['S'])

    print('Finish of get item function for: ', item)
    return {
        'name': saved_item['name']['S'],
        'origin': saved_item['origin']['S'],
        'distance': distance,
        'emissions': emissions,
        'lead_time': lead_time,
    }


async def get_route_info(leg):
    print('Start of get route function for: ', leg)
    route_origin = leg['M']['origin']['S']
    route_destination = leg['M']['destination']['S']

    print('Start of route query')
    route_result = dynamodb_client.get_item(
        TableName=ROUTE_TABLE, Key={'origin': {'S': route_origin}, 'destination': {'S': route_destination}}
    )
    print('Finish of route query')
    route = route_result.get('Item')
    if not route:
        return jsonify({
            'error': f'Could not find route with origin "{route_origin}" and destination "{route_destination}"'}), 404
    print('Finish of get route function for: ', leg)
    return route


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
        TableName=ROUTE_TABLE,
        Item={'origin': {'S': origin}, 'destination': {'S': destination}, 'origin_lat_lng': {'S': origin_lat_lng},
              'destination_lat_lng': {'S': destination_lat_lng}, 'lead_time': {'S': lead_time},
              'transport_mode': {'S': transport_mode}, 'distance': {'S': distance}, 'emissions': {'S': emissions},
              'coordinates': {'L': coordinates}}
    )
    return jsonify({'message': 'Route added successfully'})


@app.route('/route/<string:name>/<string:origin>', methods=['GET'])
def get_route(name, origin):
    result = dynamodb_client.get_item(
        TableName=ITEM_TABLE, Key={'name': {'S': name}, 'origin': {'S': origin}}
    )
    item = result.get('Item')
    if not item:
        return jsonify({'error': 'Could not find food item with provided "name and origin"'}), 404
    legs_dynamodb = item['legs']['L']
    legs = [{'origin': leg['M']['origin']['S'], 'destination': leg['M']['destination']['S']} for leg in legs_dynamodb]
    items = []
    distance = 0
    emissions = 0
    lead_time = 0
    points = []
    for leg in legs:
        route_origin = leg.get('origin')
        route_destination = leg.get('destination')
        route_result = dynamodb_client.get_item(
            TableName=ROUTE_TABLE, Key={'origin': {'S': route_origin}, 'destination': {'S': route_destination}}
        )
        item = route_result.get('Item')
        if not item:
            return jsonify({'error': 'Could not find route with provided "origin" and "destination"'}), 404
        coordinates = []
        for coord in item.get('coordinates').get('L'):
            coordinates.append([float(coord['L'][0]['N']), float(coord['L'][1]['N'])])
        items.append(
            {'origin': item.get('origin').get('S'), 'destination': item.get('destination').get('S'),
             'origin_lat_lng': item.get('origin_lat_lng').get('S'),
             'destination_lat_lng': item.get('destination_lat_lng').get('S'),
             'lead_time': item.get('lead_time').get('S'),
             'transport_mode': item.get('transport_mode').get('S'), 'distance': (item.get('distance').get('S')),
             'emissions': item.get('emissions').get('S'), 'coordinates': coordinates}
        )
        origin_lat_lng = item.get('origin_lat_lng').get('S')
        destination_lat_lng = item.get('destination_lat_lng').get('S')
        if origin_lat_lng not in points:
            points.append(origin_lat_lng)
        if destination_lat_lng not in points:
            points.append(destination_lat_lng)
        distance += int(item.get('distance').get('S'))
        emissions += int(item.get('emissions').get('S'))
        lead_time += int(item.get('lead_time').get('S'))
    return jsonify(items, {'total_distance': distance}, {'total_emissions': emissions},
                   {'total_lead_time': lead_time}, {'points': list(points)}, {'name': name}, {'origin': origin})


@app.errorhandler(404)
def resource_not_found(e):
    return make_response(jsonify(error='Not found!'), 404)

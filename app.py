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


@app.route('/shoppingList/details/<string:userId>')
def get_list_details(userId):
    # get all the items in the shopping list belonging to the user
    result = dynamodb_client.query(
        TableName=SHOPPING_LIST_TABLE,
        KeyConditionExpression='userId = :userId',
        ExpressionAttributeValues={
            ':userId': {'S': userId}
        }
    )
    # initialising totals for the whole shopping list
    total_distance = 0
    total_emissions = 0
    total_lead_time = 0
    items = result.get("Items")
    # for each item in the list
    for item in items:
        # splitting itemId into name and origin
        name = item.get('itemId').get('S').split(',')[0]
        origin = item.get('itemId').get('S').split(',')[1]
        # retrieving the item to get the legs of the journey
        item_result = dynamodb_client.get_item(
            TableName=ITEM_TABLE, Key={'name': {'S': name}, 'origin': {'S': origin}}
        )
        item_details = item_result.get('Item')
        if not item_details:
            return jsonify({'error': f'Could not find food item with name "{name}" and origin "{origin}"'}), 404
        legs_dynamodb = item_details['legs']['L']
        legs = [{'origin': leg['M']['origin']['S'], 'destination': leg['M']['destination']['S']} for leg in
                legs_dynamodb]
        # initialising totals for the food item
        distance = 0
        emissions = 0
        lead_time = 0
        # for each leg of the journey adding the distance, emissions and lead time
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
        # appending the item details to the item
        item['itemDetails'] = {
            'name': name,
            'origin': origin,
            'distance': distance,
            'emissions': emissions,
            'lead_time': lead_time,
        }
        # adding the distance, emissions and lead time of each food item to the shopping list total
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
    items = request.json.get('items')
    if not items:
        return jsonify({'error': 'Please provide "items"'}), 400
    # get the time the list is saved at
    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # item to be stored in the database consisting of the userId,
    # the time the list was saved along with the shopping list items ids
    new_item = {
        'userId': {'S': userId},
        'createdAt': {'S': current_time},
        'items': {'L': []}
    }
    # for each item in the list appending the itemId to the list of itemIds to be stored in the database
    for item in items:
        item_id = {
            'itemId': {'S': item.get('itemId').get('S')},
        }
        new_item['items']['L'].append({'M': item_id})
    # saving the shopping list to the table of saved shopping lists
    dynamodb_client.put_item(
        TableName=SAVED_LIST_TABLE, Item=new_item
    )
    # deleting all the items in the SHOPPING_LIST_TABLE associated with the userId to start a new shopping list
    for item in items:
        item_id = item.get('itemId').get('S')
        dynamodb_client.delete_item(
            TableName=SHOPPING_LIST_TABLE,
            Key={
                'userId': {'S': userId},
                'itemId': {'S': item_id}
            }
        )
    return jsonify({'message': 'Items saved successfully'})


@app.route('/savedList/list/<string:userId>', methods=['GET'])
async def get_saved_list(userId):
    # retrieve all saved lists for the user
    result = dynamodb_client.query(
        TableName=SAVED_LIST_TABLE,
        KeyConditionExpression='userId = :userId',
        ExpressionAttributeValues={
            ':userId': {'S': userId}
        }
    )
    saved_lists = []
    # for each saved list
    for saved_list in result['Items']:
        saved_items = saved_list['items']['L']
        # asynchronously getting the item details of each item in the saved list
        items = await asyncio.gather(*[create_list_item(item) for item in saved_items])

        # totals to keep track of distance, emissions and lead time for entire saved list
        total_distance = 0
        total_emissions = 0
        total_lead_time = 0

        # appending to the totals the distance, emissions and lead time of each item
        for item in items:
            total_distance += item['distance']
            total_emissions += item['emissions']
            total_lead_time += item['lead_time']

        # creating a dictionary of the details for a saved list
        shopping_list = {
            'createdAt': saved_list['createdAt']['S'],
            'items_list': items,
            'total_distance': total_distance,
            'total_emissions': total_emissions,
            'total_lead_time': total_lead_time
        }
        # appending the saved list to the list of saved shopping lists
        saved_lists.append(shopping_list)
    return jsonify(saved_lists)


async def create_list_item(item):
    name = item['M']['itemId']['S'].split(',')[0]
    origin = item['M']['itemId']['S'].split(',')[1]
    # get the item from the item table to get the legs
    result = dynamodb_client.get_item(
        TableName=ITEM_TABLE, Key={'name': {'S': name}, 'origin': {'S': origin}}
    )
    saved_item = result['Item']
    if not saved_item:
        return jsonify({'error': f'Could not find food item with name "{name}" and origin "{origin}"'}), 404

    legs = saved_item['legs']['L']

    # asynchronously gathers route information for each leg of the journey
    routes = await asyncio.gather(*[get_route_info(leg) for leg in legs])

    # total distance, emissions and lead time for a food item
    distance = 0
    emissions = 0
    lead_time = 0

    # appending distance, emissions and lead time of each leg of the journey to the food item's total
    for route in routes:
        distance += int(route['distance']['S'])
        emissions += int(route['emissions']['S'])
        lead_time += int(route['lead_time']['S'])
    # return a dictionary with a food item's details
    return {
        'name': saved_item['name']['S'],
        'origin': saved_item['origin']['S'],
        'distance': distance,
        'emissions': emissions,
        'lead_time': lead_time,
    }


async def get_route_info(leg):
    route_origin = leg['M']['origin']['S']
    route_destination = leg['M']['destination']['S']
    # get route details for a leg of the journey
    route_result = dynamodb_client.get_item(
        TableName=ROUTE_TABLE, Key={'origin': {'S': route_origin}, 'destination': {'S': route_destination}}
    )
    route = route_result.get('Item')
    if not route:
        return jsonify({
            'error': f'Could not find route with origin "{route_origin}" and destination "{route_destination}"'}), 404
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
    # first letter of items stored in the database has capital letter
    # calling method to convert request params to correct format if not already correct
    name = capitalize_first_letter(name)
    origin = capitalize_first_letter(origin)
    # getting the item with provided name and origin
    result = dynamodb_client.get_item(
        TableName=ITEM_TABLE, Key={'name': {'S': name}, 'origin': {'S': origin}}
    )
    item = result.get('Item')
    # if an item with the name and origin does not exist, returning a 404 error
    # with tailored suggestions of other searches
    if not item:
        suggestions = get_suggestions(name, origin)
        return jsonify({'error': f'Could not find food item with name "{name}" and origin "{origin}"',
                        'suggestions': suggestions}), 404
    # getting legs of journey in the food item
    legs_dynamodb = item['legs']['L']
    legs = [{'origin': leg['M']['origin']['S'], 'destination': leg['M']['destination']['S']} for leg in legs_dynamodb]
    items = []
    # variables to store accumulative distance, emissions and lead time
    distance = 0
    emissions = 0
    lead_time = 0
    points = []
    # getting details of each leg of the journey
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
        # converting coordinates into the correct format to be used in creating the map
        for coord in item.get('coordinates').get('L'):
            coordinates.append([float(coord['L'][0]['N']), float(coord['L'][1]['N'])])
        # appending to an items list json objects containing the information for each leg of the journey
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
        # creating the set of intermediate destination points
        if origin_lat_lng not in points:
            points.append(origin_lat_lng)
        if destination_lat_lng not in points:
            points.append(destination_lat_lng)
        # accumulating total distance, emissions and lead time for a food item journey
        distance += int(item.get('distance').get('S'))
        emissions += int(item.get('emissions').get('S'))
        lead_time += int(item.get('lead_time').get('S'))
    return jsonify(items, {'total_distance': distance}, {'total_emissions': emissions},
                   {'total_lead_time': lead_time}, {'points': list(points)}, {'name': name}, {'origin': origin})


def capitalize_first_letter(s):
    return s[0].upper() + s[1:]


def get_suggestions(name, origin):
    result = dynamodb_client.scan(
        TableName=ITEM_TABLE,
        FilterExpression='#name = :name OR origin = :origin',
        ExpressionAttributeValues={
            ':name': {'S': name},
            ':origin': {'S': origin}
        },
        ExpressionAttributeNames={
            '#name': 'name'
        }
    )
    items = result.get('Items')
    suggestions = []
    for item in items:
        suggestions.append({'name': item['name']['S'], 'origin': item['origin']['S']})
    if not items:
        return []
    return suggestions


@app.errorhandler(404)
def resource_not_found(e):
    return make_response(jsonify(error='Not found!'), 404)

import requests
from datetime import datetime
from traceback import print_exc
import logging
import sys


def initialize_logger():
    logger = logging.getLogger()
    logging.basicConfig(level=logging.INFO,
                        filename=f'prb_cleanup_{datetime.now().strftime("%Y-%m-%d_%H%M%S")}.log',
                        filemode='a')
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    logger.addHandler(console)

    return logger


def get_open_problems(headers, old_prbs, offboarded_prbs, patching_prbs, prbs_to_keep, logger):
    logger.info('Collecting problem tickets from Freshservice...')

    depts_url = 'https://2ndwatchhelpdesk.freshservice.com/api/v2/departments'
    prb_url = 'https://2ndwatchhelpdesk.freshservice.com/api/v2/problems'

    params = {
        'per_page': '100',
        'page': '1'
    }

    departments = {'0': '<no longer exists>'}

    # Get client names and department numbers
    try:
        depts_response = requests.get(depts_url, headers=headers, params=params)
        if depts_response.status_code == 200:
            # Parsing the JSON response
            depts_data = depts_response.json()

            for dept in depts_data['departments']:
                departments[str(dept['id'])] = dept['name']

    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")

    # for item in departments.items():
    #     logger.info(item)

    offboarded_client_depts = [17000255896, 17000033214, 17000033215, 17000033237, 17000531317, 17000033245,
                               17000035799, 17000177279, 17000033259, 17000033278, 17000033279, 0]
    found = 0
    page = 1

    more_pages = True

    # Use for looping through all pages of problem tickets
    while more_pages:
        # Sending GET request with headers
        response = requests.get(prb_url, headers=headers, params=params)

        # Checking if the request was successful (status code 200)
        if response.status_code == 200:
            # Parsing the JSON response
            data = response.json()
            found += len(data['problems'])

            # Pagination
            # print(response.headers)
            if 'Link' in response.headers:
                print(f'   {found} problems found. Processing...')
                page += 1
                params['page'] = str(page)
            else:
                more_pages = False

            try:
                for prb in data['problems']:
                    # Ignore closed PRBs
                    if prb['status'] > 1:
                        continue

                    prb_id = prb['id']
                    prb_created = prb['created_at']
                    prb_dept = prb['department_id']
                    if not prb_dept:
                        prb_dept = 0
                    prb_category = prb['category']
                    if not prb_category:
                        prb_category = 'None'

                    logger.info(f'      PRB {prb_id}: {prb["subject"]}')

                    # Filter: created prior to 2022
                    if prb_created[:4] < '2022':
                        logger.info(f'         PRB {prb_id} was created prior to 2022 ({prb_created}) and can be '
                                    f'resolved.')
                        old_prbs.append(prb_id)
                        continue
                    # Filter: offboarded clients
                    elif prb_dept in offboarded_client_depts or not prb_dept:
                        logger.info(f'         Client {departments[str(prb_dept)]} has been offboarded. PRB '
                                    f'{prb_id} can be resolved.')
                        offboarded_prbs.append(prb_id)
                        continue
                    # Filter: patching ticket
                    elif 'Patching' in prb_category:
                        logger.info(f'         PRB {prb_id} is a Patching ticket and can be resolved.')
                        patching_prbs.append(prb_id)
                        continue
                    else:
                        logger.info(f'         PRB {prb_id} did not meet the filter criteria and should be kept.')
                        prbs_to_keep.append(prb_id)

            except KeyError:
                logger.warning(f'      There was an error processing the PRB:\n      {print_exc()}')
                sys.exit(1)

        else:
            print(f"Request failed with status code: {response.status_code}")

    return old_prbs, offboarded_prbs, patching_prbs, prbs_to_keep


def close_problems(headers, old_prbs, offboarded_prbs, patching_prbs, logger):
    logger.info('Closing problem tickets...')
    closed_count = 0
    not_closed = []

    prbs_to_resolve = old_prbs + offboarded_prbs + patching_prbs

    for prb_id in prbs_to_resolve:
        sandbox_url = f'https://2ndwatchhelpdesk-fs-sandbox.freshservice.com/api/v2/problems/{prb_id}'
        url = f'https://2ndwatchhelpdesk.freshservice.com/api/v2/problems/{prb_id}'

        if prb_id in old_prbs:
            message = "PRB created prior to 2022"
            root_cause = "Unable to determine"
            impact = message
            symptoms = "See description"
        elif prb_id in offboarded_prbs:
            message = "Client offboarded"
            root_cause = "Unable to determine"
            impact = "Not applicable - client offboarded"
            symptoms = "Unable to determine"
        elif prb_id in patching_prbs:
            message = "Patching PRB addressed via another platform"
            root_cause = 'Likely SSM- or Infraguard-related'
            impact = "Patching event impeded"
            symptoms = "Patching failed or not 100% successful"
        else:
            logger.warning(f'   PRB {prb_id} not found in one of the lists. Aborting.')
            sys.exit(1)

        # status: 3 = Closed, 6 = Resolved
        json_data = {
            "status": 6,
            "known_error": True,
            "custom_fields": {
                "resolution_summary": message,
                "rca_status": "Completed",
                "known_issue": True
            },
            "analysis_fields": {
                "problem_cause": {
                    "description": root_cause
                }, "problem_symptom": {
                    "description": symptoms
                }, "problem_impact": {
                    "description": impact
                }
            }
        }

        response = requests.put(sandbox_url, headers=headers, json=json_data)

        if response.status_code == 200:
            # Parsing the JSON response
            data = response.json()

            try:
                if prb_id == data['problem']['id']:
                    logger.info(f'   PRB {prb_id} has been successfully resolved.')
                    closed_count += 1
            except KeyError:
                logger.warning('   Something went wrong.')
                not_closed.append(prb_id)
        else:
            logger.warning(f'There was a request error:\n{response.json()}')

    return closed_count, not_closed


def main():
    api_key = 'NmoxMjl2THVwMU9tTjBrUG5oRA=='
    sandbox_api_key = 'VHA1S2xiRTlTOUNmTDY1ZGc1WA=='
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Basic {sandbox_api_key}'
    }

    # For testing PRB closure in Sandbox
    old_prbs = [1]
    offboarded_prbs = [2]
    patching_prbs = [3]
    prbs_to_keep = [4]

    logger = initialize_logger()

    # old_prbs, offboarded_prbs, patching_prbs, prbs_to_keep = get_open_problems(headers, old_prbs, offboarded_prbs,
    #                                                                            patching_prbs, prbs_to_keep, logger)

    close = len(old_prbs) + len(offboarded_prbs) + len(patching_prbs)
    keeps = len(prbs_to_keep)
    logger.info(f'\nThere are {close + keeps} total open PRBs:\n   {keeps} PRBs to keep and '
                f'{close} PRBs to resolve.')

    closed, not_closed = close_problems(headers, old_prbs, offboarded_prbs, patching_prbs, logger)
    logger.info(f'\n{closed} PRBs were resolved. {close - closed} PRBs were not resolved: {not_closed}')


main()

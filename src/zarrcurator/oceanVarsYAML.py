import os
import sys

import json
import yaml
import numpy as np
from collections import defaultdict


# Input file path
oceanVarsFile = "/work/bk1414/k204247/WWE/tutorials/packemsExercises/ngc4_archival/zarrcurator/ocean_variable_list.txt"

# Formatted read from the file
data = np.genfromtxt( oceanVarsFile, dtype=None, encoding = 'utf8',
                      names=[
                             'code1','discpline','parameterCategory','parameterNumber',
                             'variableName', 
                             'units',
                             'cfName',
                             'longName',
                             'outputGroups' 
                      ],
                      # Format from FORTRAN -- a3,3i4,1x,a32,1x,a12,1x,a36,1x,a72,1x,a72   
                      delimiter=[ 3,4,4,4,  # a3,3i4
                                  1,32,     # 1x,a32
                                  1,12,     # 1x,a12
                                  1,36,     # 1x,a36
                                  1,72,     # 1x,a72
                                  1,72      # 1x,a72
                      ],
                      # skipping the columns corresponding to space ' '
                      usecols=[ 0,1,2,3,
                                5,
                                7,
                                9,
                                11,
                                13 ],
                      # Stripping the leading white spaces ' ', trailing commas ',' 
                      converters = {
                            5: lambda s: s.lstrip(' '),
                            7: lambda s: s.lstrip(' '),
                            9: lambda s: s.lstrip(' '),
                            11: lambda s: s.lstrip(' '),
                            13: lambda s: s.lstrip(' ').rstrip(','),
                      }
                     )

#Convert to dictionary 
dictdata = defaultdict(dict)
for row in data:
    
    dictdata[ row['variableName'] ] ['type'] = row['code1'][0] 
    dictdata[ row['variableName'] ] ['horizontalStaggering'] = row['code1'][1] 
    dictdata[ row['variableName'] ] ['verticalStaggering'] = row['code1'][2] 

    dictdata[ row['variableName'] ] ['discpline'] = row['discpline'] 
    dictdata[ row['variableName'] ] ['parameterCategory'] = row['parameterCategory'] 
    dictdata[ row['variableName'] ] ['parameterNumber'] = row['parameterNumber'] 
    
    dictdata[ row['variableName'] ] ['units'] = row['units']
    dictdata[ row['variableName'] ] ['cfName'] = row['cfName']
    dictdata[ row['variableName'] ] ['longName'] = row['longName']
    dictdata[ row['variableName'] ] ['outputGroups'] = row['outputGroups']

# Using 'default=int' to avoid the error "TypeError: Object of type int64 is not JSON serializable"
jsondata = json.loads(json.dumps(dictdata,default=int))

#Create the yaml file
with open('ocean_variable_list.yaml', 'w') as f:
    yaml.safe_dump(jsondata, f, default_flow_style=False)
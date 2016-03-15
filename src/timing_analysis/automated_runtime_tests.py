#
#   Copyright (c) 2010-2016, MIT Probabilistic Computing Project
#
#   Lead Developers: Dan Lovell and Jay Baxter
#   Authors: Dan Lovell, Baxter Eaves, Jay Baxter, Vikash Mansinghka
#   Research Leads: Vikash Mansinghka, Patrick Shafto
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
from __future__ import print_function
import os
import csv
import argparse
import tempfile
import time
from collections import namedtuple
import itertools
#
import numpy
#
import crosscat.utils.data_utils as du
import crosscat.utils.file_utils as fu
import crosscat.utils.hadoop_utils as hu
import crosscat.utils.xnet_utils as xu
import crosscat.LocalEngine as LE
import crosscat.HadoopEngine as HE
import crosscat.settings as S
import crosscat.cython_code.State as State
import parse_timing

def generate_hadoop_dicts(which_kernels, timing_run_parameters, args_dict):
    for which_kernel in which_kernels:
        kernel_list = (which_kernel, )
        dict_to_write = dict(timing_run_parameters)
        dict_to_write.update(args_dict)
        # must write kernel_list after update
        dict_to_write['kernel_list'] = kernel_list
        yield dict_to_write

def write_hadoop_input(input_filename, timing_run_parameters, n_steps, SEED):
    # prep settings dictionary
    time_analyze_args_dict = xu.default_analyze_args_dict
    time_analyze_args_dict['command'] = 'time_analyze'
    time_analyze_args_dict['SEED'] = SEED
    time_analyze_args_dict['n_steps'] = n_steps
    # one kernel per line
    all_kernels = State.transition_name_to_method_name_and_args.keys()
    with open(input_filename, 'a') as out_fh:
        dict_generator = generate_hadoop_dicts(all_kernels,timing_run_parameters, time_analyze_args_dict)
        for dict_to_write in dict_generator:
            xu.write_hadoop_line(out_fh, key=dict_to_write['SEED'], dict_to_write=dict_to_write)

def find_regression_coeff(filename, parameter_list, regression_file='daily_regression_coeffs.csv'):

    # Find regression coefficients from the times stored in the parsed csv files
    num_cols = 20
    # Read the csv file
    with open(filename) as fh:
        csv_reader = csv.reader(fh)
        header = csv_reader.next()[:num_cols]
        timing_rows = [row[:num_cols] for row in csv_reader]

    
    num_rows_list = parameter_list[0]
    num_cols_list = parameter_list[1]
    num_clusters_list = parameter_list[2]
    num_views_list = parameter_list[3]


    # Compute regression coefficients over all kernels
    all_kernels = State.transition_name_to_method_name_and_args.keys()
    
    with open(regression_file, 'a') as outfile:
         csvwriter=csv.writer(outfile,delimiter=',')
         
         for kernelindx in range(len(all_kernels)):
             curr_kernel = all_kernels[kernelindx]
             curr_timing_rows = [timing_rows[tmp] for tmp in range(len(timing_rows)) if timing_rows[tmp][5] == curr_kernel]
             # Iterate over the parameter values and finding matching indices in the timing data
             take_product_of = [num_rows_list, num_cols_list, num_clusters_list, num_views_list]
             count = -1
             a_list = []
             b_list = []
             #a_matrix = numpy.ones((len(num_rows_list)*len(num_cols_list)*len(num_clusters_list)*len(num_views_list), 5))
             #b_matrix = numpy.zeros((len(num_rows_list)*len(num_cols_list)*len(num_clusters_list)*len(num_views_list), 1))

             times_only = numpy.asarray([float(curr_timing_rows[i][4]) for i in range(len(curr_timing_rows))])
 
             
             for num_rows, num_cols, num_clusters, num_views in itertools.product(*take_product_of):
                 matchlist = [i for i in range(len(curr_timing_rows)) if curr_timing_rows[i][0] == str(num_rows) and \
                                  curr_timing_rows[i][1]== str(num_cols) and \
                                  curr_timing_rows[i][2]== str(num_clusters) and \
                                  curr_timing_rows[i][3]== str(num_views)]
                 if matchlist != []:
                     for matchindx in range(len(matchlist)):
                         a_list.append([1, num_rows, num_cols*num_clusters, num_rows*num_cols*num_clusters, num_views*num_rows*num_cols])
                         b_list.append(times_only[matchlist[matchindx]])

             a_matrix = numpy.asarray(a_list)
             b_matrix = numpy.asarray(b_list)
             
             x, j1, j2, j3 = numpy.linalg.lstsq(a_matrix,b_matrix)
             csvwriter.writerow([time.ctime(), curr_kernel, x[0], x[1], x[2], x[3], x[4]])
   

if __name__ == '__main__':
    default_num_rows_list = [100, 400, 1000, 4000, 10000]
    default_num_cols_list = [4, 8, 16, 24, 32]
    default_num_clusters_list = [10, 20, 40, 50]
    default_num_splits_list = [2, 3, 4]
    #
    parser = argparse.ArgumentParser()
    parser.add_argument('--gen_seed', type=int, default=0)
    parser.add_argument('--n_steps', type=int, default=10)
    parser.add_argument('--which_engine_binary', type=str,
            default=S.Hadoop.default_engine_binary)
    parser.add_argument('-do_local', action='store_true')
    parser.add_argument('-do_remote', action='store_true')
    parser.add_argument('--num_rows_list', type=int, nargs='*',
            default=default_num_rows_list)
    parser.add_argument('--num_cols_list', type=int, nargs='*',
            default=default_num_cols_list)
    parser.add_argument('--num_clusters_list', type=int, nargs='*',
            default=default_num_clusters_list)
    parser.add_argument('--num_splits_list', type=int, nargs='*',
            default=default_num_splits_list)
    #
    args = parser.parse_args()
    gen_seed = args.gen_seed
    n_steps = args.n_steps
    do_local = args.do_local
    do_remote = args.do_remote
    num_rows_list = args.num_rows_list
    num_cols_list = args.num_cols_list
    num_clusters_list = args.num_clusters_list
    num_splits_list = args.num_splits_list
    which_engine_binary = args.which_engine_binary
    #
    print('using num_rows_list: %s' % num_rows_list)
    print('using num_cols_list: %s' % num_cols_list)
    print('using num_clusters_list: %s' % num_clusters_list)
    print('using num_splits_list: %s' % num_splits_list)
    print('using engine_binary: %s' % which_engine_binary)
    time.sleep(2)


    script_filename = 'hadoop_line_processor.py'
    # some hadoop processing related settings
    dirname = 'runtime_analysis'
    fu.ensure_dir(dirname)
    temp_dir = tempfile.mkdtemp(prefix='runtime_analysis_',
                                dir=dirname)
    print('using dir: %s' % temp_dir)
    #
    table_data_filename = os.path.join(temp_dir, 'table_data.pkl.gz')
    input_filename = os.path.join(temp_dir, 'hadoop_input')
    output_filename = os.path.join(temp_dir, 'hadoop_output')
    output_path = os.path.join(temp_dir, 'output')  
    parsed_out_file = os.path.join(temp_dir, 'parsed_output.csv')

    # Hard code the parameter values for now

    parameter_list = [num_rows_list, num_cols_list, num_clusters_list, num_splits_list]

    # Iterate over the parameter values and write each run as a line in the hadoop_input file
    take_product_of = [num_rows_list, num_cols_list, num_clusters_list, num_splits_list]
    for num_rows, num_cols, num_clusters, num_splits \
            in itertools.product(*take_product_of):
        if numpy.mod(num_rows, num_clusters) == 0 and numpy.mod(num_cols,num_splits)==0:
          timing_run_parameters = dict(num_rows=num_rows, num_cols=num_cols, num_views=num_splits, num_clusters=num_clusters)
          write_hadoop_input(input_filename, timing_run_parameters,  n_steps, SEED=gen_seed)

    n_tasks = len(num_rows_list)*len(num_cols_list)*len(num_clusters_list)*len(num_splits_list)*5
    # Create a dummy table data file
    table_data=dict(T=[],M_c=[],X_L=[],X_D=[])
    fu.pickle(table_data, table_data_filename)

    if do_local:
        xu.run_script_local(input_filename, script_filename, output_filename, table_data_filename)
        print('Local Engine for automated timing runs has not been completely implemented/tested')
    elif do_remote:
        hadoop_engine = HE.HadoopEngine(which_engine_binary=which_engine_binary,
                output_path=output_path,
                input_filename=input_filename,
                table_data_filename=table_data_filename)
        xu.write_support_files(table_data, hadoop_engine.table_data_filename,
                              dict(command='time_analyze'), hadoop_engine.command_dict_filename)
        hadoop_engine.send_hadoop_command(n_tasks=n_tasks)
        was_successful = hadoop_engine.get_hadoop_results()
        if was_successful:
            hu.copy_hadoop_output(hadoop_engine.output_path, output_filename)
            parse_timing.parse_timing_to_csv(output_filename, outfile=parsed_out_file)
            coeff_list = find_regression_coeff(parsed_out_file, parameter_list)

        else:
            print('remote hadoop job NOT successful')
    else:
        # print what the command would be
        hadoop_engine = HE.HadoopEngine(which_engine_binary=which_engine_binary,
                output_path=output_path,
                input_filename=input_filename,
                table_data_filename=table_data_filename)
        cmd_str = hu.create_hadoop_cmd_str(
                hadoop_engine.hdfs_uri, hadoop_engine.hdfs_dir, hadoop_engine.jobtracker_uri,
                hadoop_engine.which_engine_binary, hadoop_engine.which_hadoop_binary,
                hadoop_engine.which_hadoop_jar,
                hadoop_engine.input_filename, hadoop_engine.table_data_filename,
                hadoop_engine.command_dict_filename, hadoop_engine.output_path,
                n_tasks, hadoop_engine.one_map_task_per_line)
        print(cmd_str)

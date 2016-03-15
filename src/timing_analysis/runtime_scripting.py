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
import argparse
import tempfile
#
import numpy
#
import crosscat.utils.data_utils as du
import crosscat.utils.xnet_utils as xu
import crosscat.utils.hadoop_utils as hu
import crosscat.LocalEngine as LE
import crosscat.HadoopEngine as HE
import crosscat.cython_code.State as State
from crosscat.settings import Hadoop as hs


def get_generative_clustering(M_c, M_r, T,
                              data_inverse_permutation_indices,
                              num_clusters, num_views):
    # NOTE: this function only works because State.p_State doesn't use
    #       column_component_suffstats
    num_rows = len(T)
    num_cols = len(T[0])
    X_D_helper = numpy.repeat(range(num_clusters), (num_rows / num_clusters))
    gen_X_D = [
        X_D_helper[numpy.argsort(data_inverse_permutation_index)]
        for data_inverse_permutation_index in data_inverse_permutation_indices
        ]
    gen_X_L_assignments = numpy.repeat(range(num_views), (num_cols / num_views))
    # initialize to generate an X_L to manipulate
    local_engine = LE.LocalEngine()
    bad_X_L, bad_X_D = local_engine.initialize(M_c, M_r, T,
                                                         initialization='apart')
    bad_X_L['column_partition']['assignments'] = gen_X_L_assignments
    # manually constrcut state in in generative configuration
    state = State.p_State(M_c, T, bad_X_L, gen_X_D)
    gen_X_L = state.get_X_L()
    gen_X_D = state.get_X_D()
    # run inference on hyperparameters to leave them in a reasonable state
    kernel_list = (
        'row_partition_hyperparameters',
        'column_hyperparameters',
        'column_partition_hyperparameter',
        )
    gen_X_L, gen_X_D = local_engine.analyze(M_c, T, gen_X_L, gen_X_D, n_steps=1,
                                            kernel_list=kernel_list)
    #
    return gen_X_L, gen_X_D

def generate_clean_state(gen_seed, num_clusters,
                         num_cols, num_rows, num_splits,
                         max_mean=10, max_std=1,
                         plot=False):
    # generate the data
    T, M_r, M_c, data_inverse_permutation_indices = \
        du.gen_factorial_data_objects(gen_seed, num_clusters,
                                      num_cols, num_rows, num_splits,
                                      max_mean=10, max_std=1,
                                      send_data_inverse_permutation_indices=True)
    # recover generative clustering
    X_L, X_D = get_generative_clustering(M_c, M_r, T,
                                         data_inverse_permutation_indices,
                                         num_clusters, num_splits)
    return T, M_c, M_r, X_L, X_D

def generate_hadoop_dicts(which_kernels, X_L, X_D, args_dict):
    for which_kernel in which_kernels:
        kernel_list = (which_kernel, )
        dict_to_write = dict(X_L=X_L, X_D=X_D)
        dict_to_write.update(args_dict)
        # must write kernel_list after update
        dict_to_write['kernel_list'] = kernel_list
        yield dict_to_write

def write_hadoop_input(input_filename, X_L, X_D, n_steps, SEED):
    # prep settings dictionary
    time_analyze_args_dict = hs.default_analyze_args_dict
    time_analyze_args_dict['command'] = 'time_analyze'
    time_analyze_args_dict['SEED'] = SEED
    time_analyze_args_dict['n_steps'] = n_steps
    # one kernel per line
    all_kernels = State.transition_name_to_method_name_and_args.keys()
    n_tasks = 0
    with open(input_filename, 'w') as out_fh:
        dict_generator = generate_hadoop_dicts(all_kernels, X_L, X_D, time_analyze_args_dict)
        for dict_to_write in dict_generator:
            xu.write_hadoop_line(out_fh, key=dict_to_write['SEED'], dict_to_write=dict_to_write)
            n_tasks += 1
    return n_tasks


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--gen_seed', type=int, default=0)
    parser.add_argument('--num_clusters', type=int, default=20)
    parser.add_argument('--num_rows', type=int, default=1000)
    parser.add_argument('--num_cols', type=int, default=20)
    parser.add_argument('--num_splits', type=int, default=2)
    parser.add_argument('--n_steps', type=int, default=10)
    parser.add_argument('-do_local', action='store_true')
    parser.add_argument('-do_remote', action='store_true')
    #
    args = parser.parse_args()
    gen_seed = args.gen_seed
    num_clusters = args.num_clusters
    num_cols = args.num_cols
    num_rows = args.num_rows
    num_splits = args.num_splits
    n_steps = args.n_steps
    do_local = args.do_local
    do_remote = args.do_remote


    script_filename = 'hadoop_line_processor.py'
    # some hadoop processing related settings
    temp_dir = tempfile.mkdtemp(prefix='runtime_analysis_',
                                dir='runtime_analysis')
    print('using dir: %s' % temp_dir)
    #
    table_data_filename = os.path.join(temp_dir, 'table_data.pkl.gz')
    input_filename = os.path.join(temp_dir, 'hadoop_input')
    output_filename = os.path.join(temp_dir, 'hadoop_output')
    output_path = os.path.join(temp_dir, 'output')
    print(table_data_filename)
    # generate data
    T, M_c, M_r, X_L, X_D = generate_clean_state(gen_seed,
                                                 num_clusters,
                                                 num_cols, num_rows,
                                                 num_splits,
                                                 max_mean=10, max_std=1)

    # write table_data
    table_data = dict(M_c=M_c, M_r=M_r, T=T)
    fu.pickle(table_data, table_data_filename)
    # write hadoop input
    n_tasks = write_hadoop_input(input_filename, X_L, X_D, n_steps, SEED=gen_seed)

    # actually run
    if do_local:
        xu.run_script_local(input_filename, script_filename, output_filename, table_data_filename)
    elif do_remote:
        hadoop_engine = HE.HadoopEngine(output_path=output_path,
                                        input_filename=input_filename,
                                        table_data_filename=table_data_filename,
                                        )
        hadoop_engine.send_hadoop_command(n_tasks)
        was_successful = hadoop_engine.get_hadoop_results()
        if was_successful:
            hu.copy_hadoop_output(output_path, output_filename)
        else:
            print('remote hadoop job NOT successful')
    else:
        hadoop_engine = HE.HadoopEngine()
        # print what the command would be
        print(HE.create_hadoop_cmd_str(hadoop_engine, n_tasks=n_tasks))

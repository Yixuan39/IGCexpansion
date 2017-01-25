# A separate class to represent Pair Site Joint State IGC model (PS JS IGC models)
# PS JS IGC model = IGC model + Point mutation model
# Xiang Ji
# xji3@ncsu.edu
import sys
from IGCModel import IGCModel
from PMModel import PMModel
import numpy as np
import itertools
from copy import deepcopy
from operator import mul
from scipy.sparse import lil_matrix
import scipy.sparse.linalg
from Common import *

class PSJSModel:
    supported = ['One rate']
    # Consider only two paralog case
    def __init__(self, x_js, pm_model, n_orlg, IGC_pm, force = None, n_js = 2):
        self.n_js   = n_js            # number of contemporaneous paralog states considered on each branch
        self.x_js   = x_js            # a concatenated vector storing x_pm + x_IGC        
        self.x_pm   = None            # x_pm vector for PMModel
        self.x_IGC  = None            # x_IGC vector for IGCModel
        self.IGC_force = None         # parameter value constraints on IGC
        self.force  = force           # parameter value constraint
        self.IGC_pm = IGC_pm

        self.pm_model = pm_model      # name of point mutation model
        self.n_orlg   = n_orlg        # total number of ortholog groups

        self.PMModel  = None          # PMModel class instance for point mutation model

        self.state_space_shape = None # initialized in init_models() function

        self.init_models()


    def unpack_x_js(self, x_js):
        # first, check if the models are supported
        assert(self.pm_model in PMModel.supported)
        assert(self.IGC_pm in PSJSModel.supported)
        if self.pm_model == 'HKY':
            num_x_pm = 4
        else:
            sys.exit( 'The point mutation model is not supported.')

        if self.IGC_pm == 'One rate':
            num_x_IGC = 2
        else:
            sys.exit( 'The IGC parameterization has not been implemented.')
            
        self.x_pm = x_js[:num_x_pm]
        self.x_IGC = x_js[num_x_pm:]
        self.x_js = x_js
        assert(num_x_pm + num_x_IGC == len(self.x_js))

    def update_by_x_js(self, new_x_js):
        self.unpack_x_js(new_x_js)
        self.PMModel.update_by_x_pm(self.x_pm)


    def divide_force(self):
        if self.force == None:
            return None, None
        # first, check if the models are supported
        assert(self.pm_model in PMModel.supported)
        assert(self.IGC_pm in PSJSModel.supported)
        if self.pm_model == 'HKY':
            num_x_pm = 4
        else:
            sys.exit('The point mutation model is not supported.')

        if self.IGC_pm == 'One rate':
            num_x_IGC = 2
        else:
            sys.exit( 'The IGC parameterization has not been implemented.')

        pm_force = dict()
        IGC_force = dict()
        for key in self.force:
            if key < num_x_pm:
                pm_force[key] = self.force[key]
            else:
                IGC_force[key - num_x_pm] = self.force[key]

        if not pm_force.keys():
            pm_force = None
        if not IGC_force.keys():
            IGC_force = None

        return pm_force, IGC_force

    def init_models(self):
        self.unpack_x_js(self.x_js)
        if self.pm_model == 'HKY':
            self.state_space_shape = [4 for i in range(self.n_js * 2)]
        else:
            sys.exit('The point mutation model has not been implemented.')

        pm_force, IGC_force = self.divide_force()
        self.PMModel = PMModel(self.pm_model, self.x_pm, pm_force)
        self.IGC_force = IGC_force
        assert( len(set(self.state_space_shape)) == 1) # now consider only same state space model
        self.update_by_x_js(self.x_js)

    def is_transition_compatible(self, transition):
        # only consider two paralogs for now
        assert(len(self.state_space_shape) == 4)
        assert(len(transition) == 2)
        state_from, state_to = transition
        assert(len(state_from) == len(state_to) == len(self.state_space_shape))
        if state_from == state_to:
            return False

        # state = (ia, ib, ja, jb) with two paralogs i, j and two positions a, b
        # Now get positions in state that are different in state_from, state_to
        pos_list = [i for i in range(len(state_from)) if state_from[i] != state_to[i]]
        if len(pos_list) > 2:
            return False
        elif len(pos_list) == 2: # only IGC can copy two sites over 
            if pos_list == [0, 1] and state_to[0] == state_from[2] and state_to[1] == state_from[3] \
               or pos_list == [2, 3] and state_to[2] == state_from[0] and state_to[3] == state_from[1]:
                return True
            else:
                return False
        elif len(pos_list) == 1: # one state change can be from mutation / IGC
            return True
        else:
            sys.exit('Check is_transition_compatible function in PSJSModel class.')
        
        
    def cal_IGC_transition_rate(self, transition, n, proportion = False):
        # n is the distance between two sites
        # n = 1, 2, 3, ...
        # Transition should be compatible
        assert(self.is_transition_compatible(transition))
        
        # Now get the two states
        state_from, state_to = transition

        # Get positions in the state that differ
        pos_list = [i for i in range(len(state_from)) if state_from[i] != state_to[i]]

        if self.IGC_pm == 'One rate':
            IGC_init, IGC_p = np.exp(self.x_IGC)
            # Now calculate IGC rate
            IGC_0_not_n = IGC_init / IGC_p * (1 - (1 - IGC_p) ** n)
            IGC_0_and_n = IGC_init / IGC_p * (1 - IGC_p) ** n
            if len(pos_list) == 1:
                pos = pos_list[0]
                same_paralog_other_pos, other_paralog_same_pos, other_paralog_other_pos = self.get_other_pos(pos)
                q_ij = self.PMModel.Q_mut[state_from[pos], state_to[pos]]
                if state_to[pos] == state_from[other_paralog_same_pos] \
                   and state_from[same_paralog_other_pos] == state_from[other_paralog_other_pos]:
                    q_IGC = IGC_0_not_n + IGC_0_and_n
                elif state_to[pos] == state_from[other_paralog_same_pos] \
                   and state_from[same_paralog_other_pos] != state_from[other_paralog_other_pos]:
                    q_IGC = IGC_0_not_n
                else:
                    q_IGC = 0.0
            elif len(pos_list) == 2:
                q_ij = 0.0
                if pos_list == [0, 1] and state_to[0] == state_from[2] and state_to[1] == state_from[3] \
               or pos_list == [2, 3] and state_to[2] == state_from[0] and state_to[3] == state_from[1]:
                    q_IGC = IGC_0_and_n
                else:
                    sys.exit('Transition not compatible!')
            else:
                sys.exit('Transition not compatible! 2')

            if proportion:
                return q_IGC / (q_ij + q_IGC)
            else:
                return q_ij + q_IGC

        else:
            sys.exit('Cal_IGC_transition_rate not implemented yet.')
    
    def get_IGC_transition_rates_BF(self, n, proportion = False):
        # This function is only for checking code, it should not be used in real calculation
        for state_from in itertools.product(range(self.state_space_shape[0]), repeat = self.n_js * 2):
            for state_to in itertools.product(range(self.state_space_shape[0]), repeat = self.n_js * 2):
                if self.is_transition_compatible((state_from, state_to)):
                    yield state_from, state_to, self.cal_IGC_transition_rate((state_from, state_to), n, proportion)
        
    def get_process_definition(self, n, proportion = False):
        row_states = []
        column_states = []
        transition_rates = []
        for row_state, col_state, transition_rate in self.get_IGC_transition_rates_BF(n, proportion):
            row_states.append(deepcopy(row_state))
            column_states.append(deepcopy(col_state))
            transition_rates.append(transition_rate)

        if proportion:
            process_definition = dict(
                row_states = row_states,
                column_states = column_states,
                weights = transition_rates)
        else:
            process_definition = dict(
                row_states = row_states,
                column_states = column_states,
                transition_rates = transition_rates)
        return process_definition
    
    def get_other_pos(self, pos):
        # return same_paralog_other_pos, other_paralog_same_pos, other_paralog_other_pos
        if pos == 0:
            return 1, 2, 3
        elif pos == 1:
            return 0, 3, 2
        elif pos == 2:
            return 3, 0, 1
        elif pos == 3:
            return 2, 1, 0
        else:
            sys.exit('Position out of range.')


if __name__ == '__main__':

    pm_model = 'HKY'
    x_js = np.concatenate((np.log([0.3, 0.5, 0.2, 9.5]), np.log([0.3, 1.0 / 30.0 ])))
    IGC_pm = 'One rate'
    n_orlg = 3
    test = PSJSModel(x_js, pm_model, n_orlg, IGC_pm)
    self = test

    transition = [(0, 2, 2, 3), (0, 2, 2, 1)]
    IGC_init, IGC_p = np.exp(self.x_IGC)
    n = 50

    IGC_0_not_n = IGC_init / IGC_p * (1 - (1 - IGC_p) ** n)
    IGC_0_and_n = IGC_init / IGC_p * (1 - IGC_p) ** n
    print IGC_0_not_n, IGC_0_and_n
    print test.is_transition_compatible(transition), test.cal_IGC_transition_rate(transition, n)
    print test.PMModel.Q_mut
    a = test.get_process_definition(10)







    
    

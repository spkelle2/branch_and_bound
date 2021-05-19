from queue import PriorityQueue
import unittest
from unittest.mock import patch, PropertyMock

from simple_mip_solver import BaseNode
from test_simple_mip_solver.example_models import no_branch, small_branch, \
    infeasible, random


class TestNode(unittest.TestCase):        

    def test_init(self):
        node = BaseNode(small_branch.lp, small_branch.integerIndices)
        self.assertTrue(node._lp, 'should get a model on proper instantiation')
        self.assertTrue(node.lower_bound == -float('inf'))
        self.assertFalse(node.objective_value, 'should have obj but empty')
        self.assertFalse(node.solution, 'should have solution but empty')
        self.assertFalse(node.lp_feasible, 'should have lp_feasible but empty')
        self.assertFalse(node.mip_feasible, 'should have mip_feasible but empty')
        self.assertTrue(node._epsilon > 0, 'should have epsilon > 0')
        self.assertFalse(node._b_dir, 'should have branch direction but empty')
        self.assertFalse(node._b_idx, 'should have branch index but empty')
        self.assertFalse(node._b_val, 'should have node value but empty')
        self.assertFalse(node.depth, 'should have depth but empty 0')
        self.assertTrue(node.branch_method == 'most fractional')
        self.assertTrue(node.search_method == 'best first')

    def test_init_fails_asserts(self):
        self.assertRaisesRegex(AssertionError, 'lp must be CyClpSimplex instance',
                               BaseNode, small_branch, small_branch.integerIndices)
        self.assertRaisesRegex(AssertionError, 'indices must match variables',
                               BaseNode, small_branch.lp, [4])
        self.assertRaisesRegex(AssertionError, 'indices must be distinct',
                               BaseNode, small_branch.lp, [0, 1, 1])
        self.assertRaisesRegex(AssertionError, 'lower bound must be a float or an int',
                               BaseNode, small_branch.lp, small_branch.integerIndices,
                               'five')
        self.assertRaisesRegex(AssertionError, 'none are none or all are none',
                               BaseNode, small_branch.lp, small_branch.integerIndices,
                               b_dir='up')
        self.assertRaisesRegex(AssertionError, 'branch index corresponds to integer variable if it exists',
                               BaseNode, small_branch.lp, small_branch.integerIndices,
                               b_idx=4, b_dir='up', b_val=.5)
        self.assertRaisesRegex(AssertionError, 'we can only round a variable up or down when branching',
                               BaseNode, small_branch.lp, small_branch.integerIndices,
                               b_idx=1, b_dir='sideways', b_val=.5)
        self.assertRaisesRegex(AssertionError, 'branch val should be within 1 of both bounds',
                               BaseNode, small_branch.lp, small_branch.integerIndices,
                               b_idx=1, b_dir='up', b_val=.5)
        self.assertRaisesRegex(AssertionError, 'depth is a positive integer',
                               BaseNode, small_branch.lp, small_branch.integerIndices,
                               depth=2.5)

    def test_base_bound_integer(self):
        node = BaseNode(no_branch.lp, no_branch.integerIndices)
        node._base_bound()
        self.assertTrue(node.objective_value == -2)
        self.assertTrue(all(node.solution == [1, 1, 0]))
        # integer solutions should come back as both lp and mip feasible
        self.assertTrue(node.lp_feasible)
        self.assertTrue(node.mip_feasible)

    def test_base_bound_fractional(self):
        node = BaseNode(small_branch.lp, small_branch.integerIndices)
        node._base_bound()
        self.assertTrue(node.objective_value == -2.75)
        self.assertTrue(all(node.solution == [0, 1.25, 1.5]))
        # fractional solutions should come back as lp but not mip feasible
        self.assertTrue(node.lp_feasible)
        self.assertFalse(node.mip_feasible)

    def test_base_bound_infeasible(self):
        node = BaseNode(infeasible.lp, infeasible.integerIndices)
        node._base_bound()
        # infeasible problems should come back as neither lp nor mip feasible
        self.assertFalse(node.lp_feasible)
        self.assertFalse(node.mip_feasible)

    def test_bound(self):
        # check function calls
        node = BaseNode(infeasible.lp, infeasible.integerIndices)
        with patch.object(node, '_base_bound') as bb:
            node.bound(junk='stuff')  # should work with extra args
            self.assertTrue(bb.call_count == 1, 'should call base bound')

        # check return
        node = BaseNode(infeasible.lp, infeasible.integerIndices)
        rtn = node.bound()
        self.assertTrue(isinstance(rtn, dict), 'should return dict')
        self.assertFalse(rtn, 'dict should be empty')

    def test_base_branch_fails_asserts(self):
        # branching before solving should fail
        node = BaseNode(no_branch.lp, no_branch.integerIndices)
        self.assertRaisesRegex(AssertionError, 'must solve before branching',
                               node._base_branch, idx=0)

        # branching on integer feasible node should fail
        node.bound()
        self.assertRaisesRegex(AssertionError, 'must branch on integer index',
                               node._base_branch, idx=-1)

        # branching on non integer index should fail
        self.assertRaisesRegex(AssertionError, 'index branched on must be fractional',
                               node._base_branch, idx=1)

    def test_base_branch(self):
        node = BaseNode(small_branch.lp, small_branch.integerIndices, -float('inf'))
        node.bound()
        idx = 2
        rtn = node._base_branch(2)

        # check each node
        for name, n in rtn.items():
            self.assertTrue(all(n._lp.matrix.elements == node._lp.matrix.elements))
            self.assertTrue(all(n._lp.objective == node._lp.objective))
            self.assertTrue(all(n._lp.constraintsLower == node._lp.constraintsLower))
            self.assertTrue(all(n._lp.constraintsUpper == node._lp.constraintsUpper))
            if name == 'down':
                self.assertTrue(all(n._lp.variablesUpper >= [1e10, 1e10, 1]))
                self.assertTrue(n._lp.variablesUpper[idx] == 1)
                self.assertTrue(all(n._lp.variablesLower == node._lp.variablesLower))
            else:
                self.assertTrue(all(n._lp.variablesUpper == node._lp.variablesUpper))
                self.assertTrue(all(n._lp.variablesLower == [0, 0, 2]))
            # check basis statuses work - i.e. are warm started
            for i in [0, 1]:
                self.assertTrue(all(node._lp.getBasisStatus()[i] ==
                                    n._lp.getBasisStatus()[i]), 'bases should match')

    def test_strong_branch_fails_asserts(self):
        node = BaseNode(small_branch.lp, small_branch.integerIndices)
        node.bound()
        idx = node._most_fractional_index

        # test we stay within iters and improve bound/stay same
        self.assertRaisesRegex(AssertionError, 'iterations must be positive integer',
                               node._strong_branch, idx, 2.5)

    def test_strong_branch(self):
        iters = 5
        node = BaseNode(random.lp, random.integerIndices)
        node.bound()
        idx = node._most_fractional_index

        # test we stay within iters and improve bound/stay same
        rtn = node._strong_branch(idx, iterations=iters)
        for direction, child_node in rtn.items():
            self.assertTrue(child_node._lp.iteration <= iters)
            if child_node._lp.getStatusCode() in [0, 3]:
                self.assertTrue(child_node._lp.objectiveValue >= node.objective_value)

        # test call base_branch
        node = BaseNode(random.lp, random.integerIndices)
        node.bound()
        idx = node._most_fractional_index
        children = node._base_branch(idx)
        with patch.object(node, '_base_branch') as bb:
            bb.return_value = children
            rtn = node._strong_branch(idx, iterations=iters)
            self.assertTrue(bb.called)

    def test_is_fractional_fails_asserts(self):
        node = BaseNode(small_branch.lp, small_branch.integerIndices)
        self.assertRaisesRegex(AssertionError, 'value should be a number',
                               node._is_fractional, '5')

    def test_is_fractional(self):
        node = BaseNode(small_branch.lp, small_branch.integerIndices)
        self.assertTrue(node._is_fractional(5.5))
        self.assertFalse(node._is_fractional(5))
        self.assertFalse(node._is_fractional(5.999999))
        self.assertFalse(node._is_fractional(5.000001))
        
    def test_most_fractional_index(self):
        node = BaseNode(no_branch.lp, no_branch.integerIndices)
        node.bound()
        self.assertFalse(node._most_fractional_index,
                         'int solution should have no fractional index')

        node = BaseNode(small_branch.lp, small_branch.integerIndices)
        node.bound()
        self.assertTrue(node._most_fractional_index == 2)

    def test_branch(self):
        node = BaseNode(small_branch.lp, small_branch.integerIndices)
        node.bound()

        # check function calls
        mock_pth = 'simple_mip_solver.nodes.base_node.BaseNode._most_fractional_index'
        with patch(mock_pth, new_callable=PropertyMock) as mfi, \
                patch.object(node, '_base_branch') as bb:
            node.branch(junk='stuff')  # should work with extra args
            self.assertTrue(mfi.call_count == 1, 'should call most frac idx')
            self.assertTrue(bb.call_count == 1, 'should call base branch')

        # check returns
        nodes = node.branch()
        self.assertTrue(all(isinstance(n, BaseNode) for n in nodes.values()))

    def test_lt(self):
        node1 = BaseNode(small_branch.lp, small_branch.integerIndices, -float('inf'))
        node2 = BaseNode(small_branch.lp, small_branch.integerIndices, 0)

        self.assertTrue(node1 < node2)
        self.assertFalse(node2 < node1)
        self.assertRaises(TypeError, node1.__lt__, 5)

        # make sure if we put them in PQ that they come out in the right order
        q = PriorityQueue()
        q.put(node2)
        q.put(node1)
        self.assertTrue(q.get().lower_bound < 0)
        self.assertTrue(q.get().lower_bound == 0)

    def test_eq(self):
        node1 = BaseNode(small_branch.lp, small_branch.integerIndices, -float('inf'))
        node2 = BaseNode(small_branch.lp, small_branch.integerIndices, 0)
        node3 = BaseNode(small_branch.lp, small_branch.integerIndices, 0)

        self.assertTrue(node3 == node2)
        self.assertFalse(node1 == node2)
        self.assertRaises(TypeError, node1.__eq__, 5)


if __name__ == '__main__':
    unittest.main()
#include "Data.h"
#include "GPRN.h"
#include "Nodes.h"
#include "Weights.h"

#include <iostream>
#include <fstream>
#include <cmath>
#include <Eigen/Core>
#include <Eigen/Dense>

using namespace std;
using namespace Eigen;

GPRN::GPRN()
{}

const vector<double>& t = Data::get_instance().get_t();
const vector<double>& sig = Data::get_instance().get_sig();
int N = Data::get_instance().get_t().size();

//just to compile for now
double extra_sigma;

Eigen::MatrixXd GPRN::branch(std::vector<double> vec1, std::vector<double> vec2)
//multiplication of the node with the weight
{
    Eigen::MatrixXd weight = Weights::get_instance().constant(vec1);
    Eigen::MatrixXd node = Nodes::get_instance().constant(vec2);

    return weight.cwiseProduct(node);
}

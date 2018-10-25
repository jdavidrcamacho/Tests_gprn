#ifndef DNest4_Data
#define DNest4_Data

#include <vector>
#include <algorithm>
#include <cmath>

class Data
{
    private:
        std::vector<double> t, rv, rverr, fwhm, fwhmerr, bis, biserhk, rhkerr, tt, y, sig;

    public:
        Data();
        //void load(const char* filename);
        void load(const char* filename, const char* units, int skip=2);
        int index_fibers;

        const char* datafile;
        const char* dataunits;
        int dataskip;

        // Getters
        int N() const {return t.size();}

        //time
        const std::vector<double>& get_t() const { return t; }
        double get_t_min() const { return *std::min_element(t.begin(), t.end()); }
        double get_t_max() const { return *std::max_element(t.begin(), t.end()); }
        double get_t_middle() const { return get_t_min() + 0.5*(get_t_max() - get_t_min()); }
        double get_timespan() const { return get_t_max() - get_t_min(); }

        //RVs
        const std::vector<double>& get_rv() const { return rv; }
        double get_rv_min() const { return *std::min_element(rv.begin(), rv.end()); }
        double get_rv_max() const { return *std::max_element(rv.begin(), rv.end()); }
        double get_rv_span() const { return get_rv_max() - get_rv_min(); }
        double get_rv_var() const;
        double get_rv_std() const { return std::sqrt(get_rv_var()); }

        //RVs error
        const std::vector<double>& get_rverr() const { return rverr; }

        //slope
        double topslope() const {return std::abs(get_rv_max() - get_rv_min()) / (t.back() - t.front());}

        //The fwhm, BIS, Rhk and respective errors
        const std::vector<double>& get_fwhm() const { return fwhm; }
        //const std::vector<double>& get_fwhmerr() const { return fwhmerr; }

        const std::vector<double>& get_bis() const { return bis; }
        const std::vector<double>& get_biserr() const {return biserr; }

        const std::vector<double>& get_rhk() const { return rhk; }
        const std::vector<double>& get_rhkerr() const { return rhkerr; }

        //Single vectors with RVs, fwhm, BIS and Rhk and respective errors
        std::vector<double> get_y() const;
        std::vector<double> get_sig() const;

    // Singleton
    private:
        static Data instance;
    public:
        static Data& get_instance() { return instance; }
};

#endif


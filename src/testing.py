
source_names = 'ant0_x', 'ant0_y', 'ant1_x', 'ant1_y', 'ant2_x', 'ant2_y', 'ant3_x', 'ant3_y'


def _get_ant_mapping_list():
    return source_names


def map_input_to_ant(input_n):
        """Maps an input number to an antenna string."""
        return _get_ant_mapping_list()[input_n]


def get_baseline_order():
    """
    Return the order of baseline data output by a CASPER correlator X engine.
    :return:
    """
    # TODO
    n_ants = 4
    order1 = []
    order2 = []
    for ctr1 in range(n_ants):
        print 'ctr1(%d)' % ctr1
        for ctr2 in range(int(n_ants/2), -1, -1):
            temp = (ctr1 - ctr2) % n_ants
            print '\tctr2(%d) temp(%d)' % (ctr2, temp)
            if ctr1 >= temp:
                order1.append((temp, ctr1))
            else:
                order2.append((ctr1, temp))
    order2 = [order_ for order_ in order2 if order_ not in order1]
    baseline_order = order1 + order2
    rv = []
    for baseline in baseline_order:
        rv.append((source_names[baseline[0] * 2],       source_names[baseline[1] * 2]))
        rv.append((source_names[baseline[0] * 2 + 1],   source_names[baseline[1] * 2 + 1]))
        rv.append((source_names[baseline[0] * 2],       source_names[baseline[1] * 2 + 1]))
        rv.append((source_names[baseline[0] * 2 + 1],   source_names[baseline[1] * 2]))
    return rv

print get_baseline_order()
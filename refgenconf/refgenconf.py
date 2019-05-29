#!/usr/bin/env python

from inspect import getfullargspec as finspect
import os
import warnings
import yacman
from attmap import PathExAttMap as PXAM
from collections import Mapping
from .exceptions import *
from ubiquerg import is_url
from .const import *


__all__ = ["RefGenConf", "select_genome_config"]


class RefGenConf(yacman.YacAttMap):
    """ A sort of oracle of available reference genome assembly assets """

    def __init__(self, entries=None):
        super(RefGenConf, self).__init__(entries)
        self.setdefault(CFG_GENOMES_KEY, PXAM())

    def get_asset(self, genome_name, asset_name, strict_exists=True,
                  check_exist=lambda p: os.path.exists(p) or is_url(p)):
        """
        Get an asset for a particular assembly.

        :param str genome_name: name of a reference genome assembly of interest
        :param str asset_name: name of the particular asset to fetch
        :param bool | NoneType strict_exists: how to handle case in which
            path doesn't exist; True to raise IOError, False to raise
            RuntimeWarning, and None to do nothing at all
        :param function(callable) -> bool check_exist: how to check for
            asset/path existence
        :return str: path to the asset
        :raise TypeError: if the existence check is not a one-arg function
        :raise refgenconf.MissingGenomeError: if the named assembly isn't known
            to this configuration instance
        :raise refgenconf.MissingAssetError: if the names assembly is known to
            this configuration instance, but the requested asset is unknown
        """
        if not callable(check_exist) or len(finspect(check_exist).args) != 1:
            raise TypeError("Asset existence check must be a one-arg function.")
        # is this even helpful? Just use RGC.genome_name.asset_name...
        try:
            genome = self.genomes[genome_name]
        except KeyError:
            raise MissingGenomeError(
                "Your genomes do not include {}".format(genome_name))
        try:
            path = genome[asset_name]
        except KeyError:
            raise MissingAssetError(
                "Genome {} exists, but index {} is missing".
                format(genome_name, asset_name))
        if strict_exists is not None and not check_exist(path):
            msg = "Asset may not exist: {}".format(path)
            for ext in [".tar.gz", ".tar"]:
                p_prime = path + ext
                if check_exist(p_prime):
                    msg += "; {} does exist".format(p_prime)
                    break
            if strict_exists:
                raise IOError(msg)
            else:
                warnings.warn(msg, RuntimeWarning)
        return path

    def genomes_list(self):
        """
        Get a list of this configuration's reference genome assembly IDs.

        :return Iterable[str]: list of this configuration's reference genome
            assembly IDs
        """
        return list(self.genomes.keys())

    def genomes_str(self):
        """
        Get as single string this configuration's reference genome assembly IDs.

        :return str: single string that lists this configuration's known
            reference genome assembly IDs
        """
        return ", ".join(self.genomes_list())

    def assets_dict(self):
        """
        Map each assembly name to a list of available asset names.

        :return Mapping[str, Iterable[str]]: mapping from assembly name to
            collection of available asset names.
        """
        return {g: list(assets.keys()) for g, assets in self.genomes.items()}

    def assets_str(self, offset_text="  ", asset_sep="; ",
                   genome_assets_delim=": "):
        """
        Create a block of text representing genome-to-asset mapping.

        :param str offset_text: text that begins each line of the text
            representation that's produced
        :param str asset_sep: the delimiter between names of types of assets,
            within each genome line
        :param str genome_assets_delim: the delimiter to place between
            reference genome assembly name and its list of asset names
        :return str: text representing genome-to-asset mapping
        """
        def make_line(gen, assets):
            return offset_text + "{}{}{}".format(
                gen, genome_assets_delim, asset_sep.join(list(assets)))
        return "\n".join([make_line(g, am) for g, am in self.genomes.items()])

    def list_assets_by_genome(self, genome=None):
        """
        List types/names of assets that are available for one--or all--genomes.

        :param str | NoneType genome: reference genome assembly ID, optional;
            if omitted, the full mapping from genome to asset names
        :return Iterable[str] | Mapping[str, Iterable[str]]: collection of
            asset type names available for particular reference assembly if
            one is provided, else the full mapping between assembly ID and
            collection available asset type names
        """
        return self.assets_dict() if genome is None else list(self.genomes[genome].keys())

    def list_genomes_by_asset(self, asset=None):
        """
        List assemblies for which a particular asset is available.

        :param str | NoneType asset: name of type of asset of interest, optional
        :return Iterable[str] | Mapping[str, Iterable[str]]: collection of
            assemblies for which the given asset is available; if asset
            argument is omitted, the full mapping from name of asset type to
            collection of assembly names for which the asset key is available
            will be returned.
        """
        return self._invert_genomes() \
            if not asset else [g for g, am in self.genomes.items() if asset in am]

    def _invert_genomes(self):
        """ Map each asset type/kind/name to a collection of assemblies.

        A configuration file encodes assets by genome, but in some use cases
        it's helpful to invert the direction of this mapping. The value of the
        asset key/name may differ by genome, so that information is
        necessarily lost in this inversion, but we can collect genome IDs by
        asset ID.

        :return Mapping[str, Iterable[str]] binding between asset kind/key/name
            and collection of reference genome assembly names for which the
            asset type is available
        """
        genomes = {}
        for g, am in self.genomes.items():
            for a in am.keys():
                genomes.setdefault(a, []).append(g)
        return genomes

    def update_genomes(self, genome, asset=None, data=None):
        """
        Updates the genomes in RefGenConf object at any level.
        If a requested genome-asset mapping is missing, it will be created

        :param str genome: genome to be added/updated
        :param str asset: asset to be added/updated
        :param Mapping data: data to be added/updated
        :return RefGenConf: updated object
        """
        def check(obj, datatype, name):
            if obj is None:
                return False
            if not isinstance(obj, datatype):
                raise TypeError("{} must be {}; got {}".format(
                    name, datatype.__name__, type(obj).__name__))
            return True

        if check(genome, str, "genome"):
            self[CFG_GENOMES_KEY].setdefault(genome, PXAM())
            if check(asset, str, "asset"):
                self[CFG_GENOMES_KEY][genome].setdefault(asset, PXAM())
                if check(data, Mapping, "data"):
                    self[CFG_GENOMES_KEY][genome][asset].update(data)
        return self


def select_genome_config(filename, conf_env_vars=None):
    """
    Get path to genome configuration file.

    :param str filename: name/path of genome configuration file
    :param Iterable[str] conf_env_vars: names of environment variables to
        consider; basically, a prioritized search list
    :return str: path to genome configuration file
    """
    return yacman.select_config(filename, conf_env_vars or CFG_ENV_VARS)

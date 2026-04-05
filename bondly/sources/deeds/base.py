"""Abstract base class for all deeds data providers."""
from abc import ABC, abstractmethod
from bondly.models.property import DeedsData


class DeedsClient(ABC):

    @abstractmethod
    def search_by_address(self, address: str) -> list[dict]:
        """
        Search for properties matching an address.
        Returns a list of: {erf_key, address, township, erf_number, lpi_code}
        """

    @abstractmethod
    def search_by_erf(self, erf_number: str, township: str, deeds_office: str = "") -> list[dict]:
        """Search by erf number and township."""

    @abstractmethod
    def search_by_owner(self, id_number: str) -> list[dict]:
        """Find all properties linked to an SA ID number or company reg number."""

    @abstractmethod
    def get_full_record(self, erf_key: str) -> DeedsData:
        """
        Retrieve the complete deeds record for a property.
        Returns a fully populated DeedsData object.
        """

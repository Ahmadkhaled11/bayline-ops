"""The supported delivery cities."""

from dataclasses import dataclass


@dataclass(frozen=True)
class City:
    country: str
    time_zone: str
    lane: str
    hub: str


CITIES = {
    "Alexandria": City("EG", "Africa/Cairo", "domestic", "Alexandria Hub"),
    "Cairo": City("EG", "Africa/Cairo", "domestic", "Cairo Hub"),
    "Giza": City("EG", "Africa/Cairo", "domestic", "Cairo Hub"),
    "Tanta": City("EG", "Africa/Cairo", "domestic", "Delta Hub"),
    "Mansoura": City("EG", "Africa/Cairo", "domestic", "Delta Hub"),
    "Port Said": City("EG", "Africa/Cairo", "domestic", "Delta Hub"),
    "Dubai": City("AE", "Asia/Dubai", "international", "Cairo Airport Export Desk"),
    "Riyadh": City("SA", "Asia/Riyadh", "international", "Cairo Airport Export Desk"),
    "Amman": City("JO", "Asia/Amman", "international", "Cairo Airport Export Desk"),
}

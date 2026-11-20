# Changelog

All notable changes to this project are recorded here.

## [Unreleased]

### Added
- Add a language-model client interface with replay and live clients.
- Add a message helper starter and topic scoring kit.

### Changed
- Refuse writes dated before a shipment's latest record.
- Print "1 piece" and "1 business day late" in desk output.
- Use merchant product ranges for parcel goods, weights and values, and align case records and replies with desk rules.
- Refreshed the sample data.

### Fixed
- Record a parcel's arrival at the destination hub before its delivery round.
- Match parcel replies to out-for-delivery and failed-delivery scans, and weight message shipment choices by the time remaining in each question window.
- Refuse an empty city in the command-line tool.

## [1.6.0] - 2026-10-19

### Added
- Address changes and the documents table.

### Changed
- Refreshed the sample data.

## [1.5.1] - 2026-07-19

### Fixed
- Return a clear not-found response for an unknown shipment in the HTTP service.

### Changed
- Keep database connections read-only for HTTP lookups.

## [1.5.0] - 2026-07-05

### Added
- Read-only HTTP interface for desk lookups.

## [1.4.0] - 2026-04-19

### Changed
- Store money in integer piastres. See decision 0001.

## [1.3.1] - 2026-02-15

### Fixed
- Keep a promised delivery date on a working day when a holiday follows the weekend.

### Changed
- Show the promised date beside the shipment status in desk lookups.

## [1.3.0] - 2026-02-01

### Added
- Business-day calendar with the 2026 holidays.

## [1.2.0] - 2025-11-30

### Added
- International lanes and customs events.

## [1.1.0] - 2025-08-17

### Added
- Damage, loss and delay claims.

## [1.0.1] - 2025-05-18

### Fixed
- Match customer email addresses without regard to letter case.

### Changed
- Make missing-record messages clearer in the command-line tool.

## [1.0.0] - 2025-05-04

### Added
- Desk command-line tool.

## [0.3.0] - 2025-03-09

### Added
- Returns rule and case records.

## [0.2.1] - 2025-02-02

### Fixed
- Keep recipient records separate from merchant returns-plan settings.

### Changed
- Include the customer city in desk lookup output.

## [0.2.0] - 2025-01-20

### Added
- Merchant and recipient records.

## [0.1.0] - 2024-11-18

### Added
- Shipment and tracking-event import.

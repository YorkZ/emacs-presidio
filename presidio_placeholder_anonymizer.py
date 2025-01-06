#!/usr/bin/env python

"""
Module: placeholder_anonymizer

This script performs placeholder-based anonymization and direct string-based
deanonymization. It reads text from stdin, then either:
- Anonymizes: Outputs JSON with 'anonymized_text' and writes an entity mapping
- Deanonymizes: Reads an existing entity mapping file, restores original PII
  by replacing placeholders directly (no Presidio offsets).

Usage:
  placeholder_anonymizer.py anonymize --entity-mapping-file <FILE>
  placeholder_anonymizer.py deanonymize --entity-mapping-file <FILE>

Examples:
  echo "Peter lives in London." | \
    python placeholder_anonymizer.py anonymize --entity-mapping-file my_map.json

  echo "<PERSON_0> lives in <LOCATION_0>." | \
    python placeholder_anonymizer.py deanonymize --entity-mapping-file my_map.json
"""

import sys
import json
import argparse
from pathlib import Path

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine, OperatorConfig
from presidio_anonymizer.operators import Operator, OperatorType


class PlaceholderAnonymizer(Operator):
    """
    A custom anonymizer which replaces detected entities with placeholders
    of the form <ENTITY_TYPE_index>. Maintains a mapping of placeholder->original.

    The mapping is stored in an external dict of dicts, e.g.:
    {
      "PERSON": {
         "Peter": "<PERSON_0>",
         "Heidi": "<PERSON_1>"
      },
      "LOCATION": {
         "London": "<LOCATION_0>"
      }
      ...
    }
    """

    REPLACING_FORMAT = "<{entity_type}_{index}>"

    def operate(self, text: str, params: dict = None) -> str:
        """
        Replace the entity text with a placeholder, building on existing indexes.
        """
        if not params or "entity_mapping" not in params:
            raise ValueError("Expected 'entity_mapping' in params.")

        entity_mapping = params["entity_mapping"]
        entity_type = params["entity_type"]

        # If no mapping for this entity type, start a new one
        if entity_type not in entity_mapping:
            entity_mapping[entity_type] = {}
            index = 0
        else:
            # If this string is already mapped, return the existing placeholder
            if text in entity_mapping[entity_type]:
                return entity_mapping[entity_type][text]
            # Otherwise, figure out the next index
            index = len(entity_mapping[entity_type])

        placeholder = self.REPLACING_FORMAT.format(entity_type=entity_type, index=index)
        entity_mapping[entity_type][text] = placeholder
        return placeholder

    def validate(self, params: dict = None) -> None:
        """
        Validate that we have the required parameters.
        """
        if not params or "entity_mapping" not in params:
            raise ValueError("An input dict 'entity_mapping' is required.")
        if "entity_type" not in params:
            raise ValueError("'entity_type' param is required.")

    def operator_name(self) -> str:
        return "placeholder_anonymizer"

    def operator_type(self) -> OperatorType:
        return OperatorType.Anonymize


def anonymize_text(input_text: str, mapping_file: Path) -> None:
    """
    Anonymize the input text, store the new mapping in `mapping_file`,
    and output JSON with anonymized text to stdout.

    :param input_text: The raw text (possibly containing PII)
    :param mapping_file: Path to store the JSON mapping
    """
    # Use Presidio to detect PII
    analyzer = AnalyzerEngine()
    analyzer_results = analyzer.analyze(text=input_text, language="en")

    # Use our custom PlaceholderAnonymizer
    anonymizer_engine = AnonymizerEngine()
    anonymizer_engine.add_anonymizer(PlaceholderAnonymizer)

    entity_mapping = {}

    # Perform placeholder anonymization
    anonymized_result = anonymizer_engine.anonymize(
        text=input_text,
        analyzer_results=analyzer_results,
        operators={
            "DEFAULT": OperatorConfig(
                "placeholder_anonymizer", {"entity_mapping": entity_mapping}
            )
        },
    )

    # Write out the mapping to disk
    mapping_data = {"entity_mapping": entity_mapping}
    mapping_file.write_text(json.dumps(mapping_data, indent=2), encoding="utf-8")

    # Print anonymized text as JSON
    output_dict = {"anonymized_text": anonymized_result.text}
    print(json.dumps(output_dict, indent=2))


def deanonymize_text(input_text: str, mapping_file: Path) -> None:
    """
    Deanonymize the input text by reading placeholders from `mapping_file`
    and replacing them with the original PII directly (no Presidio offsets).

    :param input_text: The anonymized (possibly LLM-revised) text
    :param mapping_file: Path to read the JSON mapping
    """
    # Read the stored placeholder mapping
    data = json.loads(mapping_file.read_text(encoding="utf-8"))
    entity_mapping = data["entity_mapping"]

    # Build a reverse map: e.g. "<PERSON_0>" -> "Peter"
    reverse_map = {}
    for entity_type, original_map in entity_mapping.items():
        for original_value, placeholder in original_map.items():
            reverse_map[placeholder] = original_value

    # Perform direct string replacement
    deanonymized_text = input_text
    for placeholder, original_value in reverse_map.items():
        deanonymized_text = deanonymized_text.replace(placeholder, original_value)

    output_dict = {"deanonymized_text": deanonymized_text}
    print(json.dumps(output_dict, indent=2))


def main():
    """
    Main entry point for placeholder_anonymizer script.
    Reads text from stdin, then either anonymizes or deanonymizes (by direct replacement).
    """
    parser = argparse.ArgumentParser(
        prog="placeholder_anonymizer.py",
        description="Perform placeholder-based anonymization and direct string-based deanonymization.",
    )
    parser.add_argument(
        "mode",
        choices=["anonymize", "deanonymize"],
        help="Specifies which action to perform.",
    )
    parser.add_argument(
        "--entity-mapping-file",
        default="~/.cache/presidio_mapping.json",
        help="Path to JSON file storing/retrieving the placeholder-to-original mapping (default: ~/.cache/presidio_mapping.json).",
    )

    args = parser.parse_args()
    input_text = sys.stdin.read().rstrip("\n")

    mapping_path = Path(args.entity_mapping_file)

    if args.mode == "anonymize":
        anonymize_text(input_text, mapping_path)
    else:
        # Directly restore placeholders without Presidio's offset-based approach
        deanonymize_text(input_text, mapping_path)


if __name__ == "__main__":
    main()

"""Focused conformance tests for the signed-checkpoint experiment."""

import csv
import json
import unittest

import experiment


class ExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.private_key = experiment.derive_signing_key()
        cls.public_key = cls.private_key.public_key()
        cls.records = experiment.ordinary_records("attack", 0)
        cls.levels = experiment.merkle_levels(cls.records)
        cls.artifact = experiment.build_artifact(cls.records, 5, cls.private_key)

    def test_all_leaf_proofs_validate(self) -> None:
        root = self.levels[-1][0]
        for index, record in enumerate(self.records):
            with self.subTest(index=index):
                proof = experiment.inclusion_proof(self.levels, index)
                self.assertTrue(experiment.verify_inclusion(record, index, proof, root))

    def test_proof_shape_and_sides_are_strict(self) -> None:
        root = self.levels[-1][0]
        proof = experiment.inclusion_proof(self.levels, 5)
        self.assertFalse(
            experiment.verify_inclusion(self.records[5], -1, proof, root)
        )
        self.assertFalse(
            experiment.verify_inclusion(self.records[5], 64, proof, root)
        )
        self.assertFalse(
            experiment.verify_inclusion(self.records[5], 5, proof[:-1], root)
        )
        proof[0] = dict(proof[0])
        proof[0]["side"] = "right"
        self.assertFalse(
            experiment.verify_inclusion(self.records[5], 5, proof, root)
        )

    def test_root_signature_and_proof_tampers_are_rejected(self) -> None:
        root_rejected, proof_rejected = experiment.tamper_sanity_checks(
            self.artifact, self.public_key
        )
        self.assertTrue(root_rejected)
        self.assertTrue(proof_rejected)

    def test_artifact_has_no_trust_key_and_rejects_noncanonical_hex(self) -> None:
        self.assertNotIn("public_key", self.artifact)
        uppercase = json.loads(json.dumps(self.artifact))
        uppercase["root"] = uppercase["root"].upper()
        self.assertFalse(experiment.verify_artifact(uppercase, self.public_key))

    def test_written_results_are_flat_and_complete(self) -> None:
        results = json.loads(experiment.RESULTS_PATH.read_text(encoding="utf-8"))
        self.assertIsInstance(results, dict)
        self.assertTrue(
            all(not isinstance(value, (list, dict)) for value in results.values())
        )
        self.assertTrue(results["hypothesis_supported"])
        with experiment.CSV_PATH.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 128)
        self.assertEqual(sum(row["class"] == "attack" for row in rows), 64)
        self.assertEqual(sum(row["class"] == "control" for row in rows), 64)


if __name__ == "__main__":
    unittest.main()

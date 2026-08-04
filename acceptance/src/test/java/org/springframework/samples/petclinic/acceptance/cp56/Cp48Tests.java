package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** cp48 fiscal-year: UPDATED by cp56 (member-id) — Unify the customerCode and membershipNumber into a single 'memberId' formatted '<REGION><FY><HASH8><CHK>' (region code, 2-digit fiscal year, 8 hex hash, 1 Luhn check digit), and remove the separate customerCode and membershipNumber fields */
@Tag("cp48")
class Cp48Tests extends AcceptanceBase {

	@Test
	void coreUpdatedBehaviour() throws Exception {
		// This rule changed. Unify the customerCode and membershipNumber into a single 'memberId' formatted '<REGION><FY><HASH8><CHK>' (region code, 2-digit fiscal year, 8 hex hash, 1 Luhn check digit), and remove the separate customerCode and membershipNumber fields.
		// TODO: assert the UPDATED behaviour of "fiscal-year" under the new spec.
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(status().is2xxSuccessful());
	}
}

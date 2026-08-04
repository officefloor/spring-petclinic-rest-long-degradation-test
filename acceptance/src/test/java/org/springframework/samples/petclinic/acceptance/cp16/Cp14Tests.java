package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** cp14 membership-number: UPDATED by cp16 (customer-code-city) — Change the customerCode format to '<CITY3>-<LAST3>-<NNNN>' where CITY3 is the upper-cased first three letters of the city, LAST3 the first three of the lastName, and NNNN a per-city 4-digit sequence (one more than the owners already in that city) */
@Tag("cp14")
class Cp14Tests extends AcceptanceBase {

	@Test
	void coreUpdatedBehaviour() throws Exception {
		// This rule changed. Change the customerCode format to '<CITY3>-<LAST3>-<NNNN>' where CITY3 is the upper-cased first three letters of the city, LAST3 the first three of the lastName, and NNNN a per-city 4-digit sequence (one more than the owners already in that city).
		// TODO: assert the UPDATED behaviour of "membership-number" under the new spec.
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(status().is2xxSuccessful());
	}
}

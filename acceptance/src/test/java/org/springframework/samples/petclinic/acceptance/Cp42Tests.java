package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp42 locality-timezone: Return 'timezone' derived from the locality/region via a region-to-timezone table, as an I... */
@Tag("cp42")
class Cp42Tests extends AcceptanceBase {

	@Test
	void coreReturnsTimezone() throws Exception {
		int id = createOwnerOk(withPostcode(ownerNode()));
		getOwner(id).andExpect(jsonPath("$.timezone").exists()); // IANA name
	}
}

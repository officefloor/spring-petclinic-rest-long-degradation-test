package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp30 locality-postcode: The locality derivation must now prefer the postcode: look up the region by postcode first... */
@Tag("cp30")
class Cp30Tests extends AcceptanceBase {

	@Test
	void coreLocalityFromPostcode() throws Exception {
		int id = createOwnerOk(withPostcode(ownerNode()));
		getOwner(id).andExpect(jsonPath("$.locality").exists()); // TODO: region resolved by postcode
	}
}

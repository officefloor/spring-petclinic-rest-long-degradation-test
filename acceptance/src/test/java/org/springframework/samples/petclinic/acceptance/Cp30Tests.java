package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** cp30 locality-postcode: locality is resolved by the postcode range first (NSW 2000-2099,
 *  VIC 3000-3099, QLD 4000-4099), falling back to the city. A VIC-range postcode on an unknown city
 *  therefore yields VIC, proving the postcode takes precedence. */
@Tag("cp30")
class Cp30Tests extends AcceptanceBase {

	@Test
	void coreRegionFromPostcodeRange() throws Exception {
		int id = createOwnerOk(knownOwner("Sydney")); // postcode 2000 -> NSW
		getOwner(id).andExpect(jsonPath("$.locality").value("NSW"));
	}

	@Test
	void functionalityPostcodePreferredOverCity() throws Exception {
		ObjectNode o = ownerNode(); // random (unknown) city
		o.put("postcode", "3000"); // VIC range
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.locality").value("VIC"));
	}
}

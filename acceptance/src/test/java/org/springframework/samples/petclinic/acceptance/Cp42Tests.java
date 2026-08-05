package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp42 timezone: 'timezone' is the IANA name from the pinned region-to-timezone table
 *  (NSW->Australia/Sydney, VIC->Australia/Melbourne, QLD->Australia/Brisbane). */
@Tag("cp42")
class Cp42Tests extends AcceptanceBase {

	@Test
	void coreReturnsTimezoneForRegion() throws Exception {
		int id = createOwnerOk(knownOwner("Sydney")); // postcode 2000 -> NSW
		getOwner(id).andExpect(jsonPath("$.locality").value("NSW"))
				.andExpect(jsonPath("$.timezone").value("Australia/Sydney"));
	}
}

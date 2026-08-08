package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** household-hash: householdId moves under the nested 'identity' object and is
 * gone from the top level. */
@Tag("cp36")
class Cp36Tests extends AcceptanceBase {

	@Test
	void coreHouseholdIdUnderIdentity() throws Exception {
		int id = createOwnerOk(structuredOwner());
		getOwner(id).andExpect(jsonPath("$.identity.householdId").isNotEmpty())
				.andExpect(jsonPath("$.householdId").doesNotExist());
	}
}

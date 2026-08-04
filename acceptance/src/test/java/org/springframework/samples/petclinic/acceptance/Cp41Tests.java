package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp41 code-collision: When the computed customerCode collides with an existing owner's customerCode, append '-<n... */
@Tag("cp41")
class Cp41Tests extends AcceptanceBase {

	@Test
	void coreDeduplicatesCustomerCode() throws Exception {
		// TODO: force a hash collision, expect "-2" suffix
		int id = createOwnerOk(withPostcode(ownerNode()));
		getOwner(id).andExpect(jsonPath("$.customerCode").exists());
	}
}

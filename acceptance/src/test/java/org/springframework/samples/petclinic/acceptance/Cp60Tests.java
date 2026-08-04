package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp60 identity-v2: Release version 2 of the owner identity. Rederive the region code, the householdId, the id... */
@Tag("cp60")
class Cp60Tests extends AcceptanceBase {

	@Test
	void coreV2GroupsIdentityAndVersions() throws Exception {
		int id = createOwnerOk(structuredOwner());
		getOwner(id).andExpect(jsonPath("$.apiVersion").value(2))
				.andExpect(jsonPath("$.identity.memberId").exists())
				.andExpect(jsonPath("$.identity.householdId").exists())
				.andExpect(jsonPath("$.memberId").doesNotExist()); // moved under identity
	}
}

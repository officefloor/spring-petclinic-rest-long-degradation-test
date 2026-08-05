package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp52 identity-key-v2, UPDATED by cp60: identityKey (rederived with the V2 tag) moves under the
 *  nested 'identity' object and is gone from the top level. */
@Tag("cp52")
class Cp52Tests extends AcceptanceBase {

	@Test
	void coreIdentityKeyUnderIdentity() throws Exception {
		int id = createOwnerOk(structuredOwner());
		getOwner(id).andExpect(jsonPath("$.identity.identityKey").isNotEmpty())
				.andExpect(jsonPath("$.identityKey").doesNotExist());
	}
}

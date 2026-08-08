package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** global-id: the memberId (successor to customerCode) is now under the nested
 * 'identity' object; the top-level memberId and customerCode are gone. */
@Tag("cp32")
class Cp32Tests extends AcceptanceBase {

	@Test
	void coreMemberIdUnderIdentity() throws Exception {
		int id = createOwnerOk(structuredOwner());
		getOwner(id).andExpect(jsonPath("$.identity.memberId").isNotEmpty())
				.andExpect(jsonPath("$.memberId").doesNotExist())
				.andExpect(jsonPath("$.customerCode").doesNotExist());
	}
}

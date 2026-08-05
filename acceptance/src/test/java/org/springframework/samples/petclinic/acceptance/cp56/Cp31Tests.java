package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp31 check-digit, UPDATED by cp56: checkDigit was derived from the customerCode, which is gone, so
 *  the standalone checkDigit field is removed (its Luhn digit is now the CHK inside the memberId). */
@Tag("cp31")
class Cp31Tests extends AcceptanceBase {

	@Test
	void coreCheckDigitRemoved() throws Exception {
		int id = createOwnerOk(knownOwner("Sydney"));
		getOwner(id).andExpect(jsonPath("$.checkDigit").doesNotExist());
	}
}
